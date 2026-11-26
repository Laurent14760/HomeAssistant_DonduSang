"""Recherche à la demande (action ``efs_dondesang.rechercher_collectes``) – logique pure.

Ce module ne dépend pas de Home Assistant : choix de la commune d'un code postal,
cache à durée de vie des réponses distantes et mise en forme de la réponse renvoyée
à la carte Lovelace. Il est testé directement (tests/test_search.py).
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
import time
from typing import Any, Callable, Generic, Hashable, TypeVar

from .parser import ParseResult, _normalize

# Durées de vie des caches de l'action (secondes).
# Les compteurs de places évoluent vite : 15 min évitent de solliciter l'API EFS à chaque
# affichage de la carte (plusieurs navigateurs, tablette murale) sans figer les données.
SEARCH_CACHE_TTL = 15 * 60
# Les communes d'un code postal ne changent pas : un jour suffit largement.
GEO_CACHE_TTL = 24 * 3600
CACHE_MAX_ENTRIES = 32

# Bornes des paramètres de l'action (identiques à celles des options de l'intégration,
# sauf le nombre de collectes : la réponse n'est pas historisée, la limite des 16 Ko
# du recorder ne s'applique donc pas).
RADIUS_MIN, RADIUS_MAX, DEFAULT_SEARCH_RADIUS = 1, 50, 10
DAYS_MIN, DAYS_MAX, DEFAULT_SEARCH_DAYS = 1, 180, 30
ITEMS_MIN, ITEMS_MAX, DEFAULT_SEARCH_ITEMS = 1, 100, 30

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class TtlCache(Generic[K, V]):
    """Petit cache LRU à durée de vie.

    ``get`` ne rend que les entrées fraîches ; ``get_stale`` rend aussi les entrées
    périmées, pour servir de repli quand l'API distante ne répond pas.
    """

    def __init__(
        self, ttl: float, max_entries: int = CACHE_MAX_ENTRIES, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._ttl = ttl
        self._max = max_entries
        self._clock = clock
        self._data: OrderedDict[K, tuple[float, V]] = OrderedDict()

    def get(self, key: K) -> V | None:
        item = self._data.get(key)
        if item is None or self._clock() - item[0] > self._ttl:
            return None
        self._data.move_to_end(key)
        return item[1]

    def get_stale(self, key: K) -> V | None:
        item = self._data.get(key)
        return item[1] if item else None

    def set(self, key: K, value: V) -> None:
        self._data[key] = (self._clock(), value)
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)

    def __len__(self) -> int:
        return len(self._data)


def search_key(latitude: float, longitude: float, radius_km: float) -> tuple[float, float, float]:
    """Clé de cache d'une recherche EFS : ~100 m de précision, rayon au km près.

    La réponse brute dépend seulement du rectangle interrogé ; type de don, horizon et
    collectes professionnelles sont filtrés ensuite. Changer ces paramètres dans la carte
    ne déclenche donc pas de nouvel appel à l'API.
    """
    return (round(latitude, 3), round(longitude, 3), float(round(radius_km)))


def choose_commune(
    communes: list[dict[str, Any]], wanted: str | None
) -> dict[str, Any] | None:
    """Commune retenue parmi celles d'un code postal.

    ``wanted`` peut être un code INSEE (« 14118 ») ou un nom, comparé sans casse,
    accents ni tirets (« bretteville l orgueilleuse » = « Bretteville-l'Orgueilleuse »).
    Sans choix, ou si le choix ne correspond à aucune commune, la première de la
    liste (ordre alphabétique) est retenue : la réponse liste les autres pour que
    la carte propose de changer.
    """
    if not communes:
        return None
    if wanted:
        target = str(wanted).strip()
        for c in communes:
            if c.get("code") and str(c["code"]) == target:
                return c
        key = _cle(target)
        for c in communes:
            if _cle(c.get("nom")) == key:
                return c
    return communes[0]


def _cle(text: Any) -> str:
    """Clé de comparaison d'un nom de commune (casse, accents, ponctuation ignorés)."""
    return " ".join("".join(ch if ch.isalnum() else " " for ch in _normalize(str(text or ""))).split())


@dataclass(frozen=True)
class Centre:
    """Point de départ de la recherche, tel que renvoyé à la carte."""

    libelle: str
    latitude: float
    longitude: float
    code_postal: str | None = None
    code_insee: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "libelle": self.libelle,
            "code_postal": self.code_postal,
            "code_insee": self.code_insee,
            "latitude": round(self.latitude, 4),
            "longitude": round(self.longitude, 4),
        }


def build_response(
    result: ParseResult,
    *,
    centre: Centre,
    communes: list[dict[str, Any]],
    radius_km: float,
    don_type: str,
    days: int,
    max_items: int,
    fetched_at: datetime | None,
    api_ok: bool,
    include_maisons: bool = True,
) -> dict[str, Any]:
    """Réponse de l'action, au même format que les attributs de ``collectes_a_venir``.

    La carte réutilise ainsi les mêmes vues, qu'elle lise une instance ou une recherche.
    """
    response: dict[str, Any] = {
        "centre": centre.as_dict(),
        # Communes couvertes par le code postal, pour proposer un autre point de départ.
        "communes": [{"nom": c.get("nom"), "code": c.get("code")} for c in communes],
        "rayon_km": radius_km,
        "type_don": don_type,
        "horizon_jours": days,
        "nombre": len(result.collectes),
        "collectes": [c.as_compact() for c in result.collectes[:max_items]],
        "derniere_mise_a_jour": fetched_at.isoformat() if fetched_at else None,
        "api_disponible": api_ok,
        "source": "api" if api_ok else "cache",
    }
    if include_maisons:
        response["maisons_du_don"] = [m.as_dict() for m in result.maisons_du_don[:5]]
    return response
