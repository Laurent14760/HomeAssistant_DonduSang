"""Résolution du point de recherche (logique pure, sans dépendance Home Assistant).

Trois sources possibles, choisies dans l'assistant ou dans « Configurer » :
- ``home``   : la position de la maison définie dans Home Assistant (suivie si elle change) ;
- ``postal`` : le centre d'une commune choisie par code postal ;
- ``entity`` : une entité géolocalisée (zone, personne, traceur), suivie en continu.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .const import (
    CONF_COMMUNE,
    CONF_ENTITY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_POSTAL_CODE,
    CONF_SOURCE,
    SOURCE_ENTITY,
    SOURCE_HOME,
    SOURCE_POSTAL,
)
from .parser import haversine_km

# Un déplacement plus court ne relance pas de recherche (l'API travaille au km près).
MOVE_THRESHOLD_KM = 3.0
# Au-delà de cet écart, une réponse en cache ne correspond plus au lieu demandé.
CACHE_MATCH_KM = 1.0
# Intervalle minimal entre deux recherches déclenchées par un déplacement.
MIN_MOVE_REFRESH_S = 600


@dataclass(frozen=True)
class Point:
    latitude: float
    longitude: float
    libelle: str

    def distance_to(self, other: "Point | tuple[float, float] | None") -> float | None:
        if other is None:
            return None
        lat, lon = (other.latitude, other.longitude) if isinstance(other, Point) else other
        return haversine_km(self.latitude, self.longitude, lat, lon)


def _coord(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # écarte NaN


def coords_from_attributes(attributes: Mapping[str, Any] | None) -> tuple[float, float] | None:
    """Coordonnées d'une entité (zone, personne, traceur), ou None si elle n'en publie pas."""
    if not attributes:
        return None
    lat, lon = _coord(attributes.get("latitude")), _coord(attributes.get("longitude"))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    if lat == 0 and lon == 0:  # position par défaut de certains traceurs
        return None
    return lat, lon


def unique_id_for(data: Mapping[str, Any]) -> str:
    """Identifiant unique d'une localisation (empêche deux instances sur le même lieu)."""
    source = data.get(CONF_SOURCE, SOURCE_POSTAL)
    if source == SOURCE_HOME:
        return "home"
    if source == SOURCE_ENTITY:
        return f"entity:{data.get(CONF_ENTITY)}"
    return f"{float(data[CONF_LATITUDE]):.3f}_{float(data[CONF_LONGITUDE]):.3f}"


def same_location(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """Deux localisations désignent-elles le même lieu ?

    Compare le lieu lui-même plutôt que l'identifiant unique, dont le format a changé
    en 1.3.0 (une instance « maison » créée avant enregistrait ses coordonnées).
    """
    sa, sb = a.get(CONF_SOURCE, SOURCE_POSTAL), b.get(CONF_SOURCE, SOURCE_POSTAL)
    if sa != sb:
        return False
    if sa == SOURCE_HOME:
        return True
    if sa == SOURCE_ENTITY:
        return a.get(CONF_ENTITY) == b.get(CONF_ENTITY)
    try:
        d = haversine_km(
            float(a[CONF_LATITUDE]), float(a[CONF_LONGITUDE]),
            float(b[CONF_LATITUDE]), float(b[CONF_LONGITUDE]),
        )
    except (KeyError, TypeError, ValueError):
        return False
    return d < 0.5


def entity_label(entity_id: str, friendly_name: str | None, home_name: str | None) -> str:
    """Nom lisible d'une entité suivie ; la zone de la maison prend le nom du domicile."""
    if entity_id == "zone.home":
        return home_name or "Maison"
    return friendly_name or entity_id


def describe(data: Mapping[str, Any], entity_name: str | None = None) -> str:
    """Libellé lisible de la localisation configurée."""
    source = data.get(CONF_SOURCE, SOURCE_POSTAL)
    if source == SOURCE_HOME:
        return "Position de la maison"
    if source == SOURCE_ENTITY:
        return entity_name or str(data.get(CONF_ENTITY))
    commune, code = data.get(CONF_COMMUNE), data.get(CONF_POSTAL_CODE)
    if commune and code:
        return f"{commune} ({code})"
    return commune or code or "Lieu personnalisé"


def should_refresh_on_move(
    current: Point | None,
    new: tuple[float, float] | None,
    seconds_since_fetch: float | None,
) -> tuple[bool, float]:
    """Décide si un déplacement doit relancer une recherche.

    Retourne (relancer, délai_en_secondes) : délai 0 = tout de suite ; délai > 0 = plus tard,
    pour respecter l'intervalle minimal entre deux appels à l'API.
    """
    if new is None:
        return False, 0.0
    if current is None:
        return True, 0.0
    moved = current.distance_to(new)
    if moved is None or moved < MOVE_THRESHOLD_KM:
        return False, 0.0
    if seconds_since_fetch is None or seconds_since_fetch >= MIN_MOVE_REFRESH_S:
        return True, 0.0
    return True, MIN_MOVE_REFRESH_S - seconds_since_fetch


def cache_matches(cache_point: tuple[float, float] | None, current: Point) -> bool:
    """La réponse en cache a-t-elle été obtenue pour ce lieu ?"""
    if cache_point is None:
        return False
    return (current.distance_to(cache_point) or 0.0) <= CACHE_MATCH_KM
