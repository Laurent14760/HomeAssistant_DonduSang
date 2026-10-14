"""Coordinateur de mise à jour : un appel API par instance et par intervalle."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import EfsApiClient, EfsApiError
from .const import (
    CONF_DON_TYPE,
    CONF_HORIZON,
    CONF_INCLUDE_PRO,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_RADIUS,
    CONF_SCAN_INTERVAL,
    DEFAULT_OPTIONS,
    DOMAIN,
    STORAGE_VERSION,
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
    nb_lieux_bruts: int = 0
    erreur: str | None = None
    extrait_brut: list[dict[str, Any]] = field(default_factory=list)


class EfsCoordinator(DataUpdateCoordinator[EfsData]):
    """Récupère, filtre et conserve les collectes EFS."""

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
        self.latitude = float(entry.data[CONF_LATITUDE])
        self.longitude = float(entry.data[CONF_LONGITUDE])
        self._client = EfsApiClient(async_get_clientsession(hass))
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._raw: dict[str, Any] | None = None
        self._raw_at: datetime | None = None
        self._failure_logged = False

    async def async_load_cache(self) -> None:
        """Recharge la dernière réponse valide (survit aux redémarrages)."""
        cached = await self._store.async_load()
        if cached and isinstance(cached.get("payload"), dict):
            self._raw = cached["payload"]
            self._raw_at = dt_util.parse_datetime(cached.get("fetched_at") or "")

    def _parse(self, payload: dict[str, Any]) -> ParseResult:
        return parse_collections(
            payload,
            center_lat=self.latitude,
            center_lon=self.longitude,
            radius_km=float(self.options[CONF_RADIUS]),
            don_type=self.options[CONF_DON_TYPE],
            include_pro=bool(self.options[CONF_INCLUDE_PRO]),
            horizon_days=int(self.options[CONF_HORIZON]),
            now=dt_util.now(),
        )

    async def _async_update_data(self) -> EfsData:
        try:
            payload = await self._client.async_search(
                self.latitude, self.longitude, float(self.options[CONF_RADIUS])
            )
        except EfsApiError as err:
            if self._raw is None:
                raise UpdateFailed(f"API EFS indisponible et aucune donnée en cache : {err}") from err
            if not self._failure_logged:
                _LOGGER.warning(
                    "API EFS indisponible (%s) ; conservation des données du %s",
                    err,
                    self._raw_at,
                )
                self._failure_logged = True
            else:
                _LOGGER.debug("API EFS toujours indisponible : %s", err)
            return self._build(self._raw, api_ok=False, source="cache", erreur=str(err))

        if self._failure_logged:
            _LOGGER.info("API EFS de nouveau disponible")
            self._failure_logged = False
        self._raw = payload
        self._raw_at = dt_util.utcnow()
        await self._store.async_save(
            {"fetched_at": self._raw_at.isoformat(), "payload": payload}
        )
        return self._build(payload, api_ok=True, source="api")

    def _build(
        self, payload: dict[str, Any], *, api_ok: bool, source: str, erreur: str | None = None
    ) -> EfsData:
        result = self._parse(payload)
        for rejet in result.rejets:
            _LOGGER.debug("Lieu écarté : %s", rejet)
        lieux = payload.get("samplingLocationCollections") or []
        return EfsData(
            result=result,
            derniere_reussite=self._raw_at,
            api_disponible=api_ok,
            source=source,
            nb_lieux_bruts=len(lieux),
            erreur=erreur,
            extrait_brut=lieux[:3],
        )

    async def async_remove_cache(self) -> None:
        await self._store.async_remove()
