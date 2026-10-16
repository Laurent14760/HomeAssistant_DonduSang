"""Coordinateur de mise à jour : un appel API par instance et par intervalle."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import EfsApiClient, EfsApiError
from .const import (
    CONF_COMMUNE,
    CONF_DON_TYPE,
    CONF_ENTITY,
    CONF_HORIZON,
    CONF_INCLUDE_PRO,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_RADIUS,
    CONF_SCAN_INTERVAL,
    CONF_SOURCE,
    DEFAULT_OPTIONS,
    DOMAIN,
    SOURCE_ENTITY,
    SOURCE_HOME,
    STORAGE_VERSION,
)
from .location import (
    Point,
    cache_matches,
    coords_from_attributes,
    describe,
    entity_label,
    should_refresh_on_move,
)
from .parser import ParseResult, parse_collections

_LOGGER = logging.getLogger(__name__)


@dataclass
class EfsData:
    """Données exposées aux entités."""

    result: ParseResult
    derniere_reussite: datetime | None
    api_disponible: bool
    source: str  # "api" ou "cache"
    centre: Point | None = None
    nb_lieux_bruts: int = 0
    erreur: str | None = None
    extrait_brut: list[dict[str, Any]] = field(default_factory=list)


class EfsCoordinator(DataUpdateCoordinator[EfsData]):
    """Récupère, filtre et conserve les collectes EFS autour du lieu configuré."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.options: dict[str, Any] = {**DEFAULT_OPTIONS, **entry.options}
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.title}",
            config_entry=entry,
            update_interval=timedelta(minutes=int(self.options[CONF_SCAN_INTERVAL])),
        )
        self.source: str = entry.data.get(CONF_SOURCE, "postal")
        self.point: Point | None = None  # lieu utilisé pour la dernière recherche
        self._client = EfsApiClient(async_get_clientsession(hass))
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._raw: dict[str, Any] | None = None
        self._raw_at: datetime | None = None
        self._raw_point: tuple[float, float] | None = None
        self._last_fetch: datetime | None = None
        self._pending_move: CALLBACK_TYPE | None = None
        self._failure_logged = False

    # Compatibilité : ces deux attributs étaient publics dans les versions précédentes.
    @property
    def latitude(self) -> float | None:
        return self.point.latitude if self.point else None

    @property
    def longitude(self) -> float | None:
        return self.point.longitude if self.point else None

    @property
    def location_label(self) -> str:
        return self.point.libelle if self.point else describe(self.config_entry.data)

    # ------------------------------------------------------------ localisation
    def _resolve_point(self) -> Point | None:
        """Position courante selon la source choisie (None si l'entité n'en publie pas)."""
        data = self.config_entry.data
        if self.source == SOURCE_HOME:
            lat, lon = self.hass.config.latitude, self.hass.config.longitude
            if lat is None or lon is None:
                return None
            return Point(float(lat), float(lon), self.hass.config.location_name or "Maison")
        if self.source == SOURCE_ENTITY:
            state = self.hass.states.get(data.get(CONF_ENTITY, ""))
            coords = coords_from_attributes(state.attributes if state else None)
            if coords is None:
                return None
            label = entity_label(state.entity_id, state.name, self.hass.config.location_name)
            return Point(coords[0], coords[1], label)
        return Point(
            float(data[CONF_LATITUDE]),
            float(data[CONF_LONGITUDE]),
            data.get(CONF_COMMUNE) or describe(data),
        )

    @callback
    def async_start_tracking(self) -> Callable[[], None]:
        """Suit l'entité choisie : un déplacement significatif relance la recherche."""
        if self.source != SOURCE_ENTITY:
            return lambda: None
        entity_id = self.config_entry.data[CONF_ENTITY]

        @callback
        def _moved(event: Event[EventStateChangedData]) -> None:
            new_state = event.data["new_state"]
            coords = coords_from_attributes(new_state.attributes if new_state else None)
            since = (
                (dt_util.utcnow() - self._last_fetch).total_seconds() if self._last_fetch else None
            )
            refresh, delay = should_refresh_on_move(self.point, coords, since)
            if not refresh or self._pending_move is not None:
                return
            if delay <= 0:
                _LOGGER.debug("%s s'est déplacé : nouvelle recherche", entity_id)
                self.hass.async_create_task(self.async_request_refresh())
                return

            @callback
            def _later(_now: datetime) -> None:
                self._pending_move = None
                self.hass.async_create_task(self.async_request_refresh())

            self._pending_move = async_call_later(self.hass, delay, _later)

        unsub = async_track_state_change_event(self.hass, [entity_id], _moved)

        def _stop() -> None:
            unsub()
            if self._pending_move:
                self._pending_move()
                self._pending_move = None

        return _stop

    # -------------------------------------------------------------- données
    async def async_load_cache(self) -> None:
        """Recharge la dernière réponse valide (survit aux redémarrages)."""
        cached = await self._store.async_load()
        if cached and isinstance(cached.get("payload"), dict):
            self._raw = cached["payload"]
            self._raw_at = dt_util.parse_datetime(cached.get("fetched_at") or "")
            pt = cached.get("point")
            if isinstance(pt, list) and len(pt) == 2:
                self._raw_point = (float(pt[0]), float(pt[1]))
            elif CONF_LATITUDE in self.config_entry.data:
                # Cache antérieur à la v1.3.0 : il a été obtenu pour le lieu enregistré.
                data = self.config_entry.data
                self._raw_point = (float(data[CONF_LATITUDE]), float(data[CONF_LONGITUDE]))

    def _parse(self, payload: dict[str, Any], point: Point) -> ParseResult:
        return parse_collections(
            payload,
            center_lat=point.latitude,
            center_lon=point.longitude,
            radius_km=float(self.options[CONF_RADIUS]),
            don_type=self.options[CONF_DON_TYPE],
            include_pro=bool(self.options[CONF_INCLUDE_PRO]),
            horizon_days=int(self.options[CONF_HORIZON]),
            now=dt_util.now(),
        )

    def _from_cache(self, point: Point, erreur: str) -> EfsData | None:
        if self._raw is None or not cache_matches(self._raw_point, point):
            return None
        return self._build(self._raw, point, api_ok=False, source="cache", erreur=erreur)

    async def _async_update_data(self) -> EfsData:
        point = self._resolve_point()
        if point is None:
            # Entité momentanément sans position (personne hors zone sans GPS, etc.) :
            # on garde le dernier lieu connu plutôt que de vider les entités.
            if self.point is not None and self.data is not None:
                _LOGGER.debug("Position indisponible, conservation du dernier lieu connu")
                return self.data
            raise UpdateFailed(
                f"Aucune position disponible pour la localisation « {describe(self.config_entry.data)} »"
            )

        try:
            payload = await self._client.async_search(
                point.latitude, point.longitude, float(self.options[CONF_RADIUS])
            )
        except EfsApiError as err:
            cached = self._from_cache(point, str(err))
            if cached is None:
                raise UpdateFailed(f"API EFS indisponible et aucune donnée en cache : {err}") from err
            if not self._failure_logged:
                _LOGGER.warning(
                    "API EFS indisponible (%s) ; conservation des données du %s", err, self._raw_at
                )
                self._failure_logged = True
            self.point = point
            return cached

        if self._failure_logged:
            _LOGGER.info("API EFS de nouveau disponible")
            self._failure_logged = False
        self.point = point
        self._raw = payload
        self._raw_at = self._last_fetch = dt_util.utcnow()
        self._raw_point = (point.latitude, point.longitude)
        await self._store.async_save(
            {
                "fetched_at": self._raw_at.isoformat(),
                "point": [point.latitude, point.longitude],
                "payload": payload,
            }
        )
        return self._build(payload, point, api_ok=True, source="api")

    def _build(
        self,
        payload: dict[str, Any],
        point: Point,
        *,
        api_ok: bool,
        source: str,
        erreur: str | None = None,
    ) -> EfsData:
        result = self._parse(payload, point)
        for rejet in result.rejets:
            _LOGGER.debug("Lieu écarté : %s", rejet)
        lieux = payload.get("samplingLocationCollections") or []
        return EfsData(
            result=result,
            derniere_reussite=self._raw_at,
            api_disponible=api_ok,
            source=source,
            centre=point,
            nb_lieux_bruts=len(lieux),
            erreur=erreur,
            extrait_brut=lieux[:3],
        )
