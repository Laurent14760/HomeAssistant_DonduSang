"""Résolution et suivi du lieu de recherche."""
from __future__ import annotations

import pytest

from conftest import location as L

CAEN = L.Point(49.1829, -0.3707, "Caen")


@pytest.mark.parametrize(
    "attrs, expected",
    [
        ({"latitude": 49.18, "longitude": -0.37}, (49.18, -0.37)),
        ({"latitude": "49.18", "longitude": "-0.37"}, (49.18, -0.37)),
        ({"latitude": None, "longitude": -0.37}, None),
        ({"friendly_name": "Laurent"}, None),          # personne sans GPS
        ({"latitude": 0, "longitude": 0}, None),        # position par défaut d'un traceur
        ({"latitude": 120, "longitude": 3}, None),      # hors bornes
        (None, None),
    ],
)
def test_coords_from_attributes(attrs, expected):
    assert L.coords_from_attributes(attrs) == expected


def test_unique_id_compatible_et_distinct():
    # Compatibilité : même format que les instances créées en 1.x par code postal.
    assert L.unique_id_for({"source": "postal", "latitude": 49.1728, "longitude": -0.4212}) == "49.173_-0.421"
    assert L.unique_id_for({"latitude": 49.1728, "longitude": -0.4212}) == "49.173_-0.421"
    assert L.unique_id_for({"source": "home"}) == "home"
    assert L.unique_id_for({"source": "entity", "entite": "person.laurent"}) == "entity:person.laurent"


def test_describe():
    assert L.describe({"source": "postal", "commune": "Caen", "code_postal": "14000"}) == "Caen (14000)"
    assert L.describe({"source": "home"}) == "Position de la maison"
    assert L.describe({"source": "entity", "entite": "zone.travail"}, "Travail") == "Travail"
    assert L.describe({"source": "entity", "entite": "zone.travail"}) == "zone.travail"


def test_deplacement_faible_ignore():
    # ~1 km : pas de nouvelle recherche
    assert L.should_refresh_on_move(CAEN, (49.19, -0.36), 5000) == (False, 0.0)


def test_deplacement_important_relance():
    # Caen → Bayeux (~27 km), dernière recherche il y a 20 min
    assert L.should_refresh_on_move(CAEN, (49.2764, -0.7024), 1200) == (True, 0.0)


def test_deplacement_important_mais_trop_tot():
    refresh, delay = L.should_refresh_on_move(CAEN, (49.2764, -0.7024), 120)
    assert refresh and delay == pytest.approx(480)


def test_deplacement_sans_position_ou_premier_point():
    assert L.should_refresh_on_move(CAEN, None, 9999) == (False, 0.0)
    assert L.should_refresh_on_move(None, (49.0, 0.0), None) == (True, 0.0)


def test_cache_correspond_au_lieu():
    assert L.cache_matches((49.1829, -0.3707), CAEN)
    assert L.cache_matches((49.186, -0.372), CAEN)          # < 1 km
    assert not L.cache_matches((49.2764, -0.7024), CAEN)    # autre ville
    assert not L.cache_matches(None, CAEN)


def test_meme_lieu():
    maison_v1 = {"source": "home", "latitude": 48.74, "longitude": 2.29}  # format avant 1.3.0
    assert L.same_location(maison_v1, {"source": "home"})
    caen = {"source": "postal", "latitude": 49.1829, "longitude": -0.3707}
    assert L.same_location(caen, {"source": "postal", "latitude": 49.184, "longitude": -0.371})
    assert not L.same_location(caen, {"source": "postal", "latitude": 49.2764, "longitude": -0.7024})
    assert L.same_location({"source": "entity", "entite": "zone.travail"}, {"source": "entity", "entite": "zone.travail"})
    assert not L.same_location({"source": "entity", "entite": "zone.home"}, {"source": "home"})
    assert not L.same_location(caen, {"source": "postal"})  # données incomplètes


def test_libelle_entite():
    assert L.entity_label("zone.home", "home", "Maison") == "Maison"
    assert L.entity_label("zone.home", "home", None) == "Maison"
    assert L.entity_label("person.laurent", "Laurent", "Maison") == "Laurent"
    assert L.entity_label("zone.travail", None, "Maison") == "zone.travail"
