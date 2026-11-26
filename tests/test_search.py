"""Tests de la recherche à la demande (action rechercher_collectes, logique pure)."""
from __future__ import annotations

from datetime import datetime, timezone
import json

from conftest import load_fixture, parser as p, search as s

CENTER = (49.1665, -0.4185)
NOW = datetime(2026, 10, 14, 14, 0, tzinfo=p.TZ)
COMMUNES = [
    {"nom": "Bretteville-l'Orgueilleuse", "code": "14098", "latitude": 49.21, "longitude": -0.51},
    {"nom": "Bretteville-sur-Odon", "code": "14101", "latitude": 49.1665, "longitude": -0.4185},
]


# --- Choix de la commune d'un code postal ----------------------------------
def test_choose_commune_default_is_first():
    assert s.choose_commune(COMMUNES, None)["code"] == "14098"


def test_choose_commune_by_insee_or_name():
    assert s.choose_commune(COMMUNES, "14101")["nom"] == "Bretteville-sur-Odon"
    # casse, accents, tirets et apostrophes indifférents
    assert s.choose_commune(COMMUNES, "BRETTEVILLE SUR ODON")["code"] == "14101"
    assert s.choose_commune(COMMUNES, "bretteville l orgueilleuse")["code"] == "14098"


def test_choose_commune_unknown_falls_back_and_empty_list():
    assert s.choose_commune(COMMUNES, "Caen")["code"] == "14098"
    assert s.choose_commune([], "Caen") is None


# --- Cache ------------------------------------------------------------------
def test_ttl_cache_fresh_stale_and_lru():
    clock = [0.0]
    cache = s.TtlCache(ttl=60, max_entries=2, clock=lambda: clock[0])
    cache.set("a", 1)
    clock[0] = 30
    assert cache.get("a") == 1
    clock[0] = 61
    assert cache.get("a") is None          # périmée…
    assert cache.get_stale("a") == 1       # …mais disponible en repli si l'API tombe
    cache.set("b", 2)
    cache.set("c", 3)                      # dépasse la capacité : « a » est évincée
    assert len(cache) == 2 and cache.get_stale("a") is None


def test_search_key_ignores_filters_and_tiny_moves():
    # Même rectangle interrogé : la réponse brute est réutilisée.
    assert s.search_key(49.16612, -0.41821, 10) == s.search_key(49.16634, -0.41838, 10.2)
    assert s.search_key(49.1665, -0.4185, 10) != s.search_key(49.1665, -0.4185, 20)


# --- Réponse ----------------------------------------------------------------
def _response(**over):
    result = p.parse_collections(
        load_fixture("searchnearpoint_14760.json"),
        center_lat=CENTER[0], center_lon=CENTER[1], radius_km=over.get("radius", 10),
        don_type=over.get("don", "sang"), include_pro=False,
        horizon_days=over.get("days", 90), now=NOW,
    )
    return s.build_response(
        result,
        centre=s.Centre("Bretteville-sur-Odon", *CENTER, code_postal="14760", code_insee="14101"),
        communes=COMMUNES,
        radius_km=over.get("radius", 10),
        don_type=over.get("don", "sang"),
        days=over.get("days", 90),
        max_items=over.get("max", 30),
        fetched_at=datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc),
        api_ok=over.get("api_ok", True),
    ), result


def test_response_matches_sensor_attributes_format():
    resp, result = _response()
    assert resp["centre"] == {
        "libelle": "Bretteville-sur-Odon", "code_postal": "14760", "code_insee": "14101",
        "latitude": 49.1665, "longitude": -0.4185,
    }
    assert resp["rayon_km"] == 10 and resp["horizon_jours"] == 90 and resp["type_don"] == "sang"
    assert resp["nombre"] == len(result.collectes) > 0
    # mêmes clés que l'attribut `collectes` du capteur « collectes à venir »
    assert set(resp["collectes"][0]) == set(result.collectes[0].as_compact())
    assert resp["communes"] == [{"nom": c["nom"], "code": c["code"]} for c in COMMUNES]
    assert resp["source"] == "api" and resp["api_disponible"] is True
    json.dumps(resp)  # sérialisable tel quel pour le WebSocket


def test_response_truncates_and_reports_total():
    resp, result = _response(max=2)
    assert len(resp["collectes"]) == 2 and resp["nombre"] == len(result.collectes)


def test_response_days_limit_and_cache_source():
    long, _ = _response(days=90)
    short, _ = _response(days=7)
    assert short["nombre"] <= long["nombre"]
    assert all(c["date"] <= "2026-10-21" for c in short["collectes"])
    stale, _ = _response(api_ok=False)
    assert stale["source"] == "cache" and stale["api_disponible"] is False
