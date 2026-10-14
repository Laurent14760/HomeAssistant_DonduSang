"""Logique métier pure (sans dépendance Home Assistant) : géométrie, parsing et filtrage.

Ce module est volontairement indépendant de Home Assistant pour être testé
directement sur des réponses JSON enregistrées.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
import math
import re
import unicodedata
from typing import Any
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Paris")
EARTH_RADIUS_KM = 6371.0
KM_PER_DEGREE = 111.0

DON_SANG = "sang"
DON_PLASMA = "plasma"
DON_PLAQUETTES = "plaquettes"

# Suffixe des compteurs et champ de lien de RDV par type de don.
DON_FIELDS: dict[str, tuple[str, str]] = {
    DON_SANG: ("ST", "urlBlood"),
    DON_PLASMA: ("PLA", "urlPlasma"),
    DON_PLAQUETTES: ("CPA", "urlPlatelet"),
}

# Mots-clés (normalisés, sans accents) identifiant une collecte réservée.
PRO_KEYWORDS = (
    "profession",
    "entreprise",
    "lycee",
    "college",
    "ecole",
    "universit",
    "scolaire",
    "administration",
    "militaire",
    "caserne",
)

STATUT_OUVERT = "Planning ouvert"
STATUT_NON_OUVERT = "Planning non ouvert"
STATUT_COMPLET = "Complet"

# Distance maximale tolérée entre un lieu et la préfecture du département
# déduit de son code postal. Au-delà, le lieu est jugé incohérent.
MAX_DEPT_DISTANCE_KM = 200.0

# Coordonnées approximatives des préfectures (métropole + Corse sous "20").
DEPT_CENTERS: dict[str, tuple[float, float]] = {
    "01": (46.21, 5.23), "02": (49.56, 3.62), "03": (46.57, 3.33), "04": (44.09, 6.24),
    "05": (44.56, 6.08), "06": (43.70, 7.27), "07": (44.74, 4.60), "08": (49.77, 4.72),
    "09": (42.97, 1.61), "10": (48.30, 4.08), "11": (43.21, 2.35), "12": (44.35, 2.57),
    "13": (43.30, 5.37), "14": (49.18, -0.37), "15": (44.93, 2.44), "16": (45.65, 0.16),
    "17": (46.16, -1.15), "18": (47.08, 2.40), "19": (45.27, 1.77), "20": (42.15, 9.10),
    "21": (47.32, 5.04), "22": (48.51, -2.76), "23": (46.17, 1.87), "24": (45.18, 0.72),
    "25": (47.24, 6.02), "26": (44.93, 4.89), "27": (49.03, 1.15), "28": (48.44, 1.49),
    "29": (48.00, -4.10), "30": (43.84, 4.36), "31": (43.60, 1.44), "32": (43.65, 0.59),
    "33": (44.84, -0.58), "34": (43.61, 3.88), "35": (48.11, -1.68), "36": (46.81, 1.69),
    "37": (47.39, 0.69), "38": (45.19, 5.72), "39": (46.67, 5.55), "40": (43.89, -0.50),
    "41": (47.59, 1.33), "42": (45.44, 4.39), "43": (45.04, 3.88), "44": (47.22, -1.55),
    "45": (47.90, 1.90), "46": (44.45, 1.44), "47": (44.20, 0.62), "48": (44.52, 3.50),
    "49": (47.47, -0.55), "50": (49.12, -1.09), "51": (48.96, 4.36), "52": (48.11, 5.14),
    "53": (48.07, -0.77), "54": (48.69, 6.18), "55": (48.77, 5.16), "56": (47.66, -2.76),
    "57": (49.12, 6.18), "58": (46.99, 3.16), "59": (50.63, 3.06), "60": (49.43, 2.08),
    "61": (48.43, 0.09), "62": (50.29, 2.78), "63": (45.78, 3.08), "64": (43.30, -0.37),
    "65": (43.23, 0.08), "66": (42.70, 2.90), "67": (48.57, 7.75), "68": (48.08, 7.36),
    "69": (45.76, 4.84), "70": (47.62, 6.15), "71": (46.31, 4.83), "72": (48.00, 0.20),
    "73": (45.57, 5.92), "74": (45.90, 6.13), "75": (48.86, 2.35), "76": (49.44, 1.10),
    "77": (48.54, 2.66), "78": (48.80, 2.13), "79": (46.32, -0.46), "80": (49.89, 2.30),
    "81": (43.93, 2.15), "82": (44.02, 1.35), "83": (43.12, 5.93), "84": (43.95, 4.81),
    "85": (46.67, -1.43), "86": (46.58, 0.34), "87": (45.83, 1.26), "88": (48.17, 6.45),
    "89": (47.80, 3.57), "90": (47.64, 6.86), "91": (48.63, 2.44), "92": (48.89, 2.21),
    "93": (48.91, 2.44), "94": (48.79, 2.46), "95": (49.04, 2.08),
}

_TIME_RE = re.compile(r"(\d{1,2})[:hH](\d{2})")
_ISO_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_FR_DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


# --------------------------------------------------------------------------- #
# Géométrie
# --------------------------------------------------------------------------- #
def radius_to_diameters(radius_km: float, latitude: float) -> tuple[float, float]:
    """Convertit un rayon (km) en diamètres (degrés) du rectangle de recherche EFS."""
    d_lat = 2 * radius_km / KM_PER_DEGREE
    cos_lat = max(math.cos(math.radians(latitude)), 0.01)
    d_lon = 2 * radius_km / (KM_PER_DEGREE * cos_lat)
    return round(d_lat, 5), round(d_lon, 5)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance orthodromique en km."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def postcode_is_coherent(post_code: str | None, lat: float, lon: float) -> bool:
    """Vérifie que les coordonnées sont plausibles pour le département du code postal.

    Cas observé : des lieux de Sophia Antipolis (06) géolocalisés près de Caen.
    Les codes inconnus ou d'outre-mer (97x) ne sont pas contrôlés.
    """
    if not post_code:
        return True
    code = str(post_code).strip()
    if len(code) == 4:  # code postal perdu son zéro initial (ex. 6560)
        code = "0" + code
    if not code[:2].isdigit():
        return True
    center = DEPT_CENTERS.get(code[:2])
    if center is None:
        return True
    return haversine_km(lat, lon, *center) <= MAX_DEPT_DISTANCE_KM


# --------------------------------------------------------------------------- #
# Conversions
# --------------------------------------------------------------------------- #
def parse_time(value: Any) -> time | None:
    """Accepte '08:30', '08:30:00', '8h30' ou un datetime ISO ('1900-01-01T08:30:00')."""
    if value in (None, ""):
        return None
    text = str(value)
    if "T" in text:
        text = text.split("T", 1)[1]
    match = _TIME_RE.search(text)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def parse_date(value: Any) -> date | None:
    """Accepte 'YYYY-MM-DD', 'YYYY-MM-DDTHH:MM:SS' ou 'DD/MM/YYYY'."""
    if value in (None, ""):
        return None
    text = str(value)
    if m := _ISO_DATE_RE.search(text):
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if m := _FR_DATE_RE.search(text):
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def is_professional(nature: str | None) -> bool:
    norm = _normalize(nature)
    return any(keyword in norm for keyword in PRO_KEYWORDS)


def _fmt_time(value: datetime) -> str:
    return value.strftime("%Hh%M")


# --------------------------------------------------------------------------- #
# Modèle
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Creneau:
    """Un créneau (matin ou après-midi) d'une collecte."""

    libelle: str
    debut: datetime
    fin: datetime


@dataclass
class Collecte:
    """Une collecte à une date donnée dans un lieu donné."""

    lieu: str
    adresse: str | None
    commune: str | None
    code_postal: str | None
    latitude: float
    longitude: float
    distance_km: float
    jour: date
    creneaux: list[Creneau]
    nature: str | None
    libelle_court: str | None
    places_totales: int | None
    places_restantes: int | None
    places_reservees: int | None
    taux_remplissage_efs: float | None
    lien_rdv: str | None

    @property
    def debut(self) -> datetime:
        return self.creneaux[0].debut

    @property
    def fin(self) -> datetime:
        return self.creneaux[-1].fin

    @property
    def planning_ouvert(self) -> bool:
        return self.places_restantes is not None

    @property
    def statut(self) -> str:
        if self.places_restantes is None:
            return STATUT_NON_OUVERT
        if self.places_restantes <= 0:
            return STATUT_COMPLET
        return STATUT_OUVERT

    @property
    def taux_remplissage(self) -> float | None:
        """Taux calculé sur les compteurs du type de don choisi (cohérent avec les places).

        À défaut de compteurs exploitables, on reprend tauxRemplissage de l'API.
        """
        if self.places_totales and self.places_restantes is not None:
            occupees = self.places_totales - self.places_restantes
            return round(100 * occupees / self.places_totales, 1)
        if self.taux_remplissage_efs is not None and self.places_totales is not None:
            taux = self.taux_remplissage_efs
            return round(taux * 100 if 0 < taux <= 1 else taux, 1)
        return None

    @property
    def horaires(self) -> str:
        return " / ".join(f"{_fmt_time(c.debut)}-{_fmt_time(c.fin)}" for c in self.creneaux)

    @property
    def texte_places(self) -> str:
        if self.places_restantes is None:
            return STATUT_NON_OUVERT
        if self.places_totales:
            return f"{self.places_restantes} places restantes sur {self.places_totales}"
        return f"{self.places_restantes} places restantes"

    def as_compact(self) -> dict[str, Any]:
        """Forme compacte pour l'attribut `collectes` (taille maîtrisée)."""
        return {
            "date": self.jour.isoformat(),
            "debut": self.debut.isoformat(),
            "horaires": self.horaires,
            "lieu": self.lieu,
            "commune": self.commune,
            "distance": self.distance_km,
            "places_totales": self.places_totales,
            "places_restantes": self.places_restantes,
            "places_reservees": self.places_reservees,
            "lien_rdv": self.lien_rdv,
        }


@dataclass
class MaisonDuDon:
    nom: str
    adresse: str | None
    commune: str | None
    code_postal: str | None
    latitude: float
    longitude: float
    distance_km: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "nom": self.nom,
            "adresse": self.adresse,
            "commune": self.commune,
            "distance": self.distance_km,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }


@dataclass
class ParseResult:
    collectes: list[Collecte] = field(default_factory=list)
    maisons_du_don: list[MaisonDuDon] = field(default_factory=list)
    rejets: list[dict[str, Any]] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def _build_slot(libelle: str, jour: date, start_raw: Any, end_raw: Any) -> Creneau | None:
    start = parse_time(start_raw)
    if start is None:
        return None
    end = parse_time(end_raw)
    debut = datetime.combine(jour, start, tzinfo=TZ)
    fin = datetime.combine(jour, end, tzinfo=TZ) if end else debut + timedelta(hours=3)
    if fin <= debut:
        fin = debut + timedelta(hours=3)
    return Creneau(libelle, debut, fin)


def _location_check(
    loc: dict[str, Any], center_lat: float, center_lon: float, radius_km: float
) -> tuple[float | None, str | None]:
    """Retourne (distance, None) si le lieu est retenu, (None, motif) sinon."""
    lat, lon = _to_float(loc.get("latitude")), _to_float(loc.get("longitude"))
    if lat is None or lon is None:
        return None, "coordonnées absentes"
    distance = haversine_km(center_lat, center_lon, lat, lon)
    if distance > radius_km:
        return None, f"hors rayon ({distance:.1f} km)"
    if not postcode_is_coherent(loc.get("postCode"), lat, lon):
        return None, f"code postal {loc.get('postCode')} incohérent avec la position"
    return round(distance, 1), None


def parse_collections(
    payload: dict[str, Any] | None,
    *,
    center_lat: float,
    center_lon: float,
    radius_km: float,
    don_type: str,
    include_pro: bool,
    horizon_days: int,
    now: datetime,
) -> ParseResult:
    """Transforme la réponse brute de l'API Carto en collectes filtrées et triées."""
    result = ParseResult()
    if not isinstance(payload, dict):
        return result

    suffix, url_field = DON_FIELDS.get(don_type, DON_FIELDS[DON_SANG])
    now = now.astimezone(TZ)
    limite = now.date() + timedelta(days=horizon_days)
    vus: set[tuple[str, date]] = set()

    for loc in payload.get("samplingLocationCollections") or []:
        name = (loc.get("name") or loc.get("city") or "Lieu inconnu").strip()
        collections = loc.get("collections") or []
        if not collections:
            continue  # lieu sans collecte : ignoré
        distance, motif = _location_check(loc, center_lat, center_lon, radius_km)
        if motif:
            result.rejets.append({"lieu": name, "code_postal": loc.get("postCode"), "motif": motif})
            continue

        for col in collections:
            jour = parse_date(col.get("date"))
            if jour is None or jour > limite:
                continue
            nature = col.get("nature") or loc.get("nature")
            if not include_pro and is_professional(nature):
                continue
            creneaux = [
                c
                for c in (
                    _build_slot("Matin", jour, col.get("morningStartTime"), col.get("morningEndTime")),
                    _build_slot("Après-midi", jour, col.get("afternoonStartTime"), col.get("afternoonEndTime")),
                )
                if c is not None
            ]
            if not creneaux or creneaux[-1].fin <= now:
                continue  # aucun créneau exploitable ou collecte terminée
            cle = (_normalize(name), jour)
            if cle in vus:
                continue
            vus.add(cle)

            result.collectes.append(
                Collecte(
                    lieu=name,
                    adresse=loc.get("fullAddress"),
                    commune=loc.get("city"),
                    code_postal=loc.get("postCode"),
                    latitude=float(loc["latitude"]),
                    longitude=float(loc["longitude"]),
                    distance_km=distance,
                    jour=jour,
                    creneaux=creneaux,
                    nature=nature,
                    libelle_court=col.get("convocationLabelSMS"),
                    places_totales=_to_int(col.get(f"nbPlacesTotales{suffix}")),
                    places_restantes=_to_int(col.get(f"nbPlacesRestantes{suffix}")),
                    places_reservees=_to_int(col.get(f"nbPlacesReservees{suffix}")),
                    taux_remplissage_efs=_to_float(col.get("tauxRemplissage")),
                    lien_rdv=col.get(url_field) or None,
                )
            )

    result.collectes.sort(key=lambda c: (c.debut, c.distance_km))

    for ent in payload.get("samplingLocationEntities_SF") or []:
        name = (ent.get("name") or "Maison du don").strip()
        distance, motif = _location_check(ent, center_lat, center_lon, radius_km)
        if motif:
            continue
        result.maisons_du_don.append(
            MaisonDuDon(
                nom=name,
                adresse=ent.get("fullAddress"),
                commune=ent.get("city"),
                code_postal=ent.get("postCode"),
                latitude=float(ent["latitude"]),
                longitude=float(ent["longitude"]),
                distance_km=distance,
            )
        )
    result.maisons_du_don.sort(key=lambda m: m.distance_km)
    return result


def next_collecte(collectes: list[Collecte], now: datetime) -> Collecte | None:
    """Première collecte non terminée (une collecte en cours reste « prochaine »)."""
    return next((c for c in collectes if c.fin > now), None)
