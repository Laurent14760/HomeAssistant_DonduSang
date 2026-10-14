"""Clients HTTP asynchrones : API Carto v3 de l'EFS et API Géo de l'État."""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .const import API_LIMIT, EFS_API_URL, GEO_API_URL, REQUEST_TIMEOUT
from .parser import radius_to_diameters

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "HomeAssistant-efs_dondesang",
}


class EfsApiError(Exception):
    """Erreur de communication avec une API distante."""


async def _get_json(
    session: aiohttp.ClientSession, url: str, params: dict[str, Any]
) -> Any:
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT):
            async with session.get(url, params=params, headers=HEADERS) as resp:
                if resp.status != 200:
                    body = (await resp.text())[:200]
                    raise EfsApiError(f"HTTP {resp.status} sur {url} : {body}")
                return await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
        raise EfsApiError(f"{type(err).__name__} sur {url} : {err}") from err


class EfsApiClient:
    """Client de l'API Carto v3 (publique, sans clé)."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def async_search(
        self, latitude: float, longitude: float, radius_km: float
    ) -> dict[str, Any]:
        d_lat, d_lon = radius_to_diameters(radius_km, latitude)
        params = {
            "CenterLatitude": round(latitude, 6),
            "CenterLongitude": round(longitude, 6),
            "DiameterLatitude": d_lat,
            "DiameterLongitude": d_lon,
            "UserLatitude": round(latitude, 6),
            "UserLongitude": round(longitude, 6),
            "Limit": API_LIMIT,
        }
        data = await _get_json(self._session, EFS_API_URL, params)
        if not isinstance(data, dict):
            raise EfsApiError("Réponse EFS inattendue (objet JSON attendu)")
        return data


async def async_search_communes(
    session: aiohttp.ClientSession, postal_code: str
) -> list[dict[str, Any]]:
    """Communes couvertes par un code postal, avec leur centre géographique."""
    data = await _get_json(
        session,
        GEO_API_URL,
        {"codePostal": postal_code, "fields": "nom,centre,code", "format": "json"},
    )
    communes: list[dict[str, Any]] = []
    for item in data or []:
        coords = (item.get("centre") or {}).get("coordinates") or []
        if len(coords) != 2:
            continue
        communes.append(
            {
                "nom": item.get("nom"),
                "code": item.get("code"),
                "longitude": float(coords[0]),
                "latitude": float(coords[1]),
            }
        )
    communes.sort(key=lambda c: c["nom"] or "")
    return communes
