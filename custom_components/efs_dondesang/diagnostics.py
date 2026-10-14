"""Diagnostics téléchargeables (Paramètres > Appareils et services > EFS > ⋮)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import EfsConfigEntry
from .const import CONF_LATITUDE, CONF_LONGITUDE

TO_REDACT = {CONF_LATITUDE, CONF_LONGITUDE}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: EfsConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    data = coordinator.data
    diag: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
        },
    }
    if data is None:
        return diag
    diag["donnees"] = {
        "source": data.source,
        "api_disponible": data.api_disponible,
        "derniere_reussite": data.derniere_reussite.isoformat() if data.derniere_reussite else None,
        "erreur": data.erreur,
        "nb_lieux_bruts": data.nb_lieux_bruts,
        "nb_collectes_retenues": len(data.result.collectes),
        "nb_maisons_du_don": len(data.result.maisons_du_don),
        "rejets": data.result.rejets,
        "collectes": [c.as_compact() for c in data.result.collectes[:10]],
        "extrait_reponse_brute": data.extrait_brut,
    }
    return diag
