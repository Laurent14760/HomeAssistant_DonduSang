"""Tests sur réponses JSON enregistrées (code postal 14760, rayon 10 km)."""
from __future__ import annotations

from datetime import date, datetime, time
import json

import pytest

from conftest import load_fixture, parser as p

CENTER = (49.1665, -0.4185)  # Bretteville-sur-Odon (API Géo)
NOW = datetime(2026, 10, 14, 14, 0, tzinfo=p.TZ)


def parse(**overrides):
    kwargs = dict(
        center_lat=CENTER[0], center_lon=CENTER[1], radius_km=10, don_type="sang",
        include_pro=False, horizon_days=90, now=NOW,
    )
    kwargs.update(overrides)
    return p.parse_collections(load_fixture("searchnearpoint_14760.json"), **kwargs)


def by_city(result, city, day=None):
    return [c for c in result.collectes if c.commune == city and (day is None or c.jour == day)]


# --- Géométrie -------------------------------------------------------------
def test_radius_to_diameters():
    d_lat, d_lon = p.radius_to_diameters(10, 49.166)
    assert d_lat == pytest.approx(0.18018, abs=1e-4)
    assert d_lon == pytest.approx(0.2755, abs=1e-3)  # 2R / (111 x cos 49.166°)


def test_haversine():
    # Caen – Bretteville-sur-Odon ≈ 4 km
    assert p.haversine_km(49.1665, -0.4185, 49.183, -0.370) == pytest.approx(3.95, abs=0.2)


def test_postcode_coherence():
    assert p.postcode_is_coherent("14760", 49.1665, -0.4185)
    assert not p.postcode_is_coherent("06560", 49.17, -0.41)  # Sophia Antipolis près de Caen
    assert not p.postcode_is_coherent("6560", 49.17, -0.41)   # zéro initial perdu
    assert p.postcode_is_coherent("97400", 49.17, -0.41)      # outre-mer non contrôlé
    assert p.postcode_is_coherent(None, 49.17, -0.41)


# --- Conversions -----------------------------------------------------------
@pytest.mark.parametrize(
    "raw, expected",
    [("08:30", time(8, 30)), ("08:30:00", time(8, 30)), ("1900-01-01T16:00:00", time(16, 0)),
     ("8h30", time(8, 30)), (None, None), ("", None), ("n/a", None)],
)
def test_parse_time(raw, expected):
    assert p.parse_time(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [("2026-11-16T00:00:00", date(2026, 11, 16)), ("2026-11-16", date(2026, 11, 16)),
     ("16/11/2026", date(2026, 11, 16)), (None, None)],
)
def test_parse_date(raw, expected):
    assert p.parse_date(raw) == expected


# --- Critères de recette ----------------------------------------------------
def test_recette_communes_et_tri():
    result = parse()
    vues = [(c.jour.isoformat(), c.commune) for c in result.collectes]
    assert vues == [
        ("2026-10-21", "Caen"),
        ("2026-10-28", "Fontaine-Étoupefour"),
        ("2026-11-05", "Bretteville-l'Orgueilleuse"),
        ("2026-11-16", "Bretteville-sur-Odon"),
        ("2026-12-14", "Bretteville-sur-Odon"),
        ("2026-12-24", "Soliers"),
    ]
    debuts = [c.debut for c in result.collectes]
    assert debuts == sorted(debuts)


def test_aucun_lieu_hors_rayon_ni_aberrant():
    result = parse()
    assert all(c.distance_km <= 10 for c in result.collectes)
    noms = {c.lieu for c in result.collectes}
    assert "Salle municipale" not in noms               # Biéville : coin du rectangle
    assert not any("Sophia" in n for n in noms)         # code postal incohérent
    assert "Salle sans collecte" not in noms
    motifs = {r["lieu"]: r["motif"] for r in result.rejets}
    assert "hors rayon" in motifs["Salle municipale"]
    assert "incohérent" in motifs["Sophia Antipolis – Site Amadeus"]


def test_collectes_passees_et_horizon():
    assert not by_city(parse(), "Bretteville-sur-Odon", date(2026, 10, 1))
    assert not [c for c in parse().collectes if c.jour.year == 2027]
    # Horizon 60 j au 14/10 : jusqu'au 13/12 inclus, le 14/12 n'est pas encore visible.
    jours = {c.jour for c in parse(horizon_days=60).collectes}
    assert date(2026, 11, 16) in jours and date(2026, 12, 14) not in jours


def test_doublons_supprimes():
    assert len(by_city(parse(), "Caen", date(2026, 10, 21))) == 1


def test_collectes_professionnelles():
    assert not [c for c in parse().collectes if c.lieu == "Lycée Jean Rostand"]
    pro = [c for c in parse(include_pro=True).collectes if c.lieu == "Lycée Jean Rostand"]
    assert len(pro) == 1 and p.is_professional(pro[0].nature)
    assert not p.is_professional("Commune")
    assert p.is_professional("Lycée")


# --- Créneaux ---------------------------------------------------------------
def test_creneau_matin_nul():
    (c,) = by_city(parse(), "Bretteville-sur-Odon", date(2026, 11, 16))
    assert [cr.libelle for cr in c.creneaux] == ["Après-midi"]
    assert c.debut == datetime(2026, 11, 16, 15, 30, tzinfo=p.TZ)
    assert c.horaires == "15h30-19h30"


def test_deux_creneaux_fuseau_paris():
    (c,) = by_city(parse(), "Fontaine-Étoupefour")
    assert len(c.creneaux) == 2
    assert c.horaires == "08h30-12h00 / 15h00-19h00"
    assert c.debut.utcoffset().total_seconds() == 3600  # 28/10 : heure d'hiver (UTC+1)


def test_creneau_format_datetime():
    (c,) = by_city(parse(), "Bretteville-l'Orgueilleuse")
    assert c.debut.time() == time(16, 0)


# --- Places -----------------------------------------------------------------
def test_places_planning_ouvert():
    (c,) = by_city(parse(), "Fontaine-Étoupefour")
    assert (c.places_totales, c.places_restantes, c.places_reservees) == (54, 39, 15)
    assert c.taux_remplissage == pytest.approx(27.8)
    assert c.statut == p.STATUT_OUVERT
    assert c.texte_places == "39 places restantes sur 54"
    assert c.lien_rdv.endswith("/sang")


def test_places_planning_non_ouvert():
    (c,) = by_city(parse(), "Soliers")
    assert c.places_totales is None and c.places_restantes is None  # unknown, pas 0
    assert c.taux_remplissage is None
    assert c.statut == p.STATUT_NON_OUVERT
    assert c.texte_places == "Planning non ouvert"
    assert c.lien_rdv is None


def test_places_complet():
    (c,) = by_city(parse(), "Caen")
    assert c.places_restantes == 0 and c.statut == p.STATUT_COMPLET
    assert c.taux_remplissage == 100


def test_bascule_type_de_don():
    (pla,) = by_city(parse(don_type="plasma"), "Fontaine-Étoupefour")
    assert (pla.places_totales, pla.places_restantes, pla.places_reservees) == (12, 5, 7)
    assert pla.lien_rdv.endswith("/plasma")
    (cpa,) = by_city(parse(don_type="plaquettes"), "Fontaine-Étoupefour")
    assert cpa.places_restantes is None and cpa.statut == p.STATUT_NON_OUVERT


# --- Prochaine collecte, attributs, Maisons du don -------------------------
def test_prochaine_collecte_en_cours_puis_suivante():
    collectes = parse().collectes
    assert p.next_collecte(collectes, NOW).commune == "Caen"
    pendant = datetime(2026, 10, 21, 10, 0, tzinfo=p.TZ)
    assert p.next_collecte(collectes, pendant).commune == "Caen"
    apres = datetime(2026, 10, 21, 13, 5, tzinfo=p.TZ)
    assert p.next_collecte(collectes, apres).commune == "Fontaine-Étoupefour"


def test_attribut_compact_sous_16ko():
    c = parse().collectes[1]
    taille = len(json.dumps([c.as_compact()] * 30, ensure_ascii=False).encode())
    assert taille < 16_000
    assert {"places_totales", "places_restantes", "places_reservees"} <= c.as_compact().keys()


def test_maisons_du_don():
    maisons = parse().maisons_du_don
    assert [m.nom for m in maisons] == ["Maison du don de Caen"]


def test_reponse_vide_ou_invalide():
    for payload in (None, {}, {"samplingLocationCollections": None}, []):
        res = p.parse_collections(
            payload, center_lat=CENTER[0], center_lon=CENTER[1], radius_km=10,
            don_type="sang", include_pro=False, horizon_days=60, now=NOW,
        )
        assert res.collectes == []


@pytest.mark.parametrize(
    "raw, expected",
    [("efs.link/fGWaH", "https://efs.link/fGWaH"), ("https://efs.link/x", "https://efs.link/x"),
     ("//efs.link/x", "https://efs.link/x"), ("", None), (None, None), ("javascript:alert(1)", None)],
)
def test_normalize_url(raw, expected):
    assert p.normalize_url(raw) == expected
