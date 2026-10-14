"""Constantes de l'intégration EFS Don de sang."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "efs_dondesang"
MANUFACTURER: Final = "Établissement français du sang"

EFS_API_URL: Final = (
    "https://oudonner.api.efs.sante.fr/carto-api/v3/samplingcollection/searchnearpoint"
)
GEO_API_URL: Final = "https://geo.api.gouv.fr/communes"
EFS_WEBSITE: Final = "https://dondesang.efs.sante.fr"
API_LIMIT: Final = 100
REQUEST_TIMEOUT: Final = 30

# Données de l'entrée (localisation, figée à l'installation)
CONF_SOURCE: Final = "source"
CONF_POSTAL_CODE: Final = "code_postal"
CONF_COMMUNE: Final = "commune"
CONF_INSEE: Final = "code_insee"
CONF_LATITUDE: Final = "latitude"
CONF_LONGITUDE: Final = "longitude"
SOURCE_HOME: Final = "home"
SOURCE_POSTAL: Final = "postal"

# Options (modifiables sans réinstaller)
CONF_RADIUS: Final = "rayon_km"
CONF_DON_TYPE: Final = "type_don"
CONF_INCLUDE_PRO: Final = "inclure_professionnelles"
CONF_HORIZON: Final = "horizon_jours"
CONF_MAX_ITEMS: Final = "max_collectes"
CONF_SCAN_INTERVAL: Final = "intervalle_minutes"
CONF_ALERT_DAYS: Final = "jours_alerte"
CONF_MAISONS_DU_DON: Final = "inclure_maisons_du_don"

DEFAULT_RADIUS: Final = 10
DEFAULT_DON_TYPE: Final = "sang"
DEFAULT_INCLUDE_PRO: Final = False
DEFAULT_HORIZON: Final = 60
DEFAULT_MAX_ITEMS: Final = 10
DEFAULT_SCAN_INTERVAL: Final = 60
DEFAULT_ALERT_DAYS: Final = 7
DEFAULT_MAISONS_DU_DON: Final = False

MAX_ITEMS_LIMIT: Final = 30  # garde l'attribut `collectes` sous la limite de 16 Ko du recorder
MIN_SCAN_INTERVAL: Final = 15

DON_TYPES: Final = ["sang", "plasma", "plaquettes"]

DEFAULT_OPTIONS: Final = {
    CONF_RADIUS: DEFAULT_RADIUS,
    CONF_DON_TYPE: DEFAULT_DON_TYPE,
    CONF_INCLUDE_PRO: DEFAULT_INCLUDE_PRO,
    CONF_HORIZON: DEFAULT_HORIZON,
    CONF_MAX_ITEMS: DEFAULT_MAX_ITEMS,
    CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
    CONF_ALERT_DAYS: DEFAULT_ALERT_DAYS,
    CONF_MAISONS_DU_DON: DEFAULT_MAISONS_DU_DON,
}

STORAGE_VERSION: Final = 1
