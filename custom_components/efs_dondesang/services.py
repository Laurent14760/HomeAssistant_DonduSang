"""Action ``efs_dondesang.rechercher_collectes`` : recherche à la demande, avec réponse.

Utilisée par la carte ``custom:efs-collectes-card`` quand on lui donne un code postal,
un rayon, un type de don et un nombre de jours : la carte n'a alors besoin d'aucune
instance dédiée à ce lieu. Également appelable depuis un script ou une automatisation
(``response_variable``).
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .api import EfsApiClient, EfsApiError, async_search_communes
from .const import DEFAULT_DON_TYPE, DOMAIN, DON_TYPES
from .parser import parse_collections
from .search import (
    DAYS_MAX,
    DAYS_MIN,
    DEFAULT_SEARCH_DAYS,
    DEFAULT_SEARCH_ITEMS,
    DEFAULT_SEARCH_RADIUS,
    GEO_CACHE_TTL,
    ITEMS_MAX,
    ITEMS_MIN,
    RADIUS_MAX,
    RADIUS_MIN,
    SEARCH_CACHE_TTL,
    COMMUNE_SEARCH_RADIUS,
    Centre,
    TtlCache,
    build_response,
    choose_commune,
    filter_commune,
    search_key,
)

_LOGGER = logging.getLogger(__name__)

SERVICE_SEARCH = "rechercher_collectes"

ATTR_POSTAL_CODE = "code_postal"
ATTR_COMMUNE = "commune"
ATTR_LATITUDE = "latitude"
ATTR_LONGITUDE = "longitude"
ATTR_RADIUS = "rayon_km"
ATTR_DON_TYPE = "type_don"
ATTR_DAYS = "jours"
ATTR_INCLUDE_PRO = "inclure_professionnelles"
ATTR_MAX_ITEMS = "max_collectes"


def _has_start_point(data: dict[str, Any]) -> dict[str, Any]:
    """Un point de départ est requis : code postal, ou latitude + longitude."""
    if data.get(ATTR_POSTAL_CODE):
        return data
    if data.get(ATTR_LATITUDE) is not None and data.get(ATTR_LONGITUDE) is not None:
        return data
    raise vol.Invalid("Indiquez un code postal, ou une latitude et une longitude")


SEARCH_SCHEMA = vol.All(
    vol.Schema(
        {
            # Code postal à 5 chiffres ; les espaces saisis (« 14 760 ») sont tolérés.
            vol.Optional(ATTR_POSTAL_CODE): vol.All(
                cv.string, lambda v: v.replace(" ", ""), vol.Match(r"^\d{5}$")
            ),
            # Nom ou code INSEE, pour les codes postaux couvrant plusieurs communes.
            vol.Optional(ATTR_COMMUNE): cv.string,
            vol.Optional(ATTR_LATITUDE): vol.All(vol.Coerce(float), vol.Range(-90, 90)),
            vol.Optional(ATTR_LONGITUDE): vol.All(vol.Coerce(float), vol.Range(-180, 180)),
            # 0 = uniquement la commune de départ (nécessite un code postal)
            vol.Optional(ATTR_RADIUS, default=DEFAULT_SEARCH_RADIUS): vol.All(
                vol.Coerce(float), vol.Range(RADIUS_MIN, RADIUS_MAX)
            ),
            vol.Optional(ATTR_DON_TYPE, default=DEFAULT_DON_TYPE): vol.In(DON_TYPES),
            vol.Optional(ATTR_DAYS, default=DEFAULT_SEARCH_DAYS): vol.All(
                vol.Coerce(int), vol.Range(DAYS_MIN, DAYS_MAX)
            ),
            vol.Optional(ATTR_INCLUDE_PRO, default=False): cv.boolean,
            vol.Optional(ATTR_MAX_ITEMS, default=DEFAULT_SEARCH_ITEMS): vol.All(
                vol.Coerce(int), vol.Range(ITEMS_MIN, ITEMS_MAX)
            ),
        }
    ),
    _has_start_point,
)


class _SearchService:
    """Porte les caches de l'action pour toute la durée de vie de Home Assistant."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._geo: TtlCache[str, list[dict[str, Any]]] = TtlCache(GEO_CACHE_TTL)
        # Valeur : (réponse brute EFS, date de récupération)
        self._payloads: TtlCache[tuple[float, float, float], tuple[dict[str, Any], Any]] = TtlCache(
            SEARCH_CACHE_TTL
        )

    async def _communes(self, postal_code: str) -> list[dict[str, Any]]:
        cached = self._geo.get(postal_code)
        if cached is not None:
            return cached
        session = async_get_clientsession(self.hass)
        try:
            communes = await async_search_communes(session, postal_code)
        except EfsApiError as err:
            stale = self._geo.get_stale(postal_code)
            if stale is not None:
                return stale
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="geo_unavailable",
                translation_placeholders={"erreur": str(err)},
            ) from err
        self._geo.set(postal_code, communes)
        return communes

    async def _payload(
        self, latitude: float, longitude: float, radius_km: float
    ) -> tuple[dict[str, Any], Any, bool]:
        """Réponse brute EFS : (payload, date de récupération, api_disponible)."""
        key = search_key(latitude, longitude, radius_km)
        cached = self._payloads.get(key)
        if cached is not None:
            return cached[0], cached[1], True
        client = EfsApiClient(async_get_clientsession(self.hass))
        try:
            payload = await client.async_search(latitude, longitude, radius_km)
        except EfsApiError as err:
            stale = self._payloads.get_stale(key)
            if stale is not None:
                _LOGGER.warning("API EFS indisponible (%s) : réponse du %s conservée", err, stale[1])
                return stale[0], stale[1], False
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="efs_unavailable",
                translation_placeholders={"erreur": str(err)},
            ) from err
        fetched_at = dt_util.utcnow()
        self._payloads.set(key, (payload, fetched_at))
        return payload, fetched_at, True

    async def async_handle(self, call: ServiceCall) -> ServiceResponse:
        data = call.data
        communes: list[dict[str, Any]] = []
        postal_code = data.get(ATTR_POSTAL_CODE)

        if postal_code:
            communes = await self._communes(postal_code)
            commune = choose_commune(communes, data.get(ATTR_COMMUNE))
            if commune is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="unknown_postal_code",
                    translation_placeholders={"code_postal": postal_code},
                )
            centre = Centre(
                libelle=commune["nom"] or postal_code,
                latitude=commune["latitude"],
                longitude=commune["longitude"],
                code_postal=postal_code,
                code_insee=commune.get("code"),
            )
        else:
            centre = Centre(
                libelle=data.get(ATTR_COMMUNE) or "Point choisi",
                latitude=data[ATTR_LATITUDE],
                longitude=data[ATTR_LONGITUDE],
            )

        radius = float(data[ATTR_RADIUS])
        commune_seule = radius == 0
        if commune_seule and not postal_code:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="radius_zero_needs_postal_code"
            )
        # Rayon 0 : recherche autour de la commune, puis filtre sur son nom.
        search_radius = float(COMMUNE_SEARCH_RADIUS) if commune_seule else radius
        payload, fetched_at, api_ok = await self._payload(
            centre.latitude, centre.longitude, search_radius
        )
        result = parse_collections(
            payload,
            center_lat=centre.latitude,
            center_lon=centre.longitude,
            radius_km=search_radius,
            don_type=data[ATTR_DON_TYPE],
            include_pro=bool(data[ATTR_INCLUDE_PRO]),
            horizon_days=int(data[ATTR_DAYS]),
            now=dt_util.now(),
        )
        if commune_seule:
            result = filter_commune(result, centre.libelle)
        return build_response(
            result,
            centre=centre,
            communes=communes,
            # Rayon renvoyé en entier quand il l'est (« 10 km » plutôt que « 10.0 km »).
            radius_km=int(radius) if radius.is_integer() else radius,
            don_type=data[ATTR_DON_TYPE],
            days=int(data[ATTR_DAYS]),
            max_items=int(data[ATTR_MAX_ITEMS]),
            fetched_at=fetched_at,
            api_ok=api_ok,
        )


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Déclare l'action (une seule fois, indépendamment des instances)."""
    if hass.services.has_service(DOMAIN, SERVICE_SEARCH):
        return
    service = _SearchService(hass)
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEARCH,
        service.async_handle,
        schema=SEARCH_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
