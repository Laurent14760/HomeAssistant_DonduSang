"""Capteur binaire : collecte dans les X prochains jours."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import EfsConfigEntry
from .const import CONF_ALERT_DAYS
from .entity import EfsEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: EfsConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([CollecteProcheBinarySensor(entry.runtime_data)])


class CollecteProcheBinarySensor(EfsEntity, BinarySensorEntity):
    _attr_icon = "mdi:water-alert"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "collecte_proche", "binary_sensor")

    @property
    def _jours(self) -> int:
        return int(self.coordinator.options[CONF_ALERT_DAYS])

    @property
    def is_on(self) -> bool:
        c = self.prochaine
        if c is None:
            return False
        limite = dt_util.now().date() + timedelta(days=self._jours)
        return c.jour <= limite

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        c = self.prochaine
        return {
            "jours_alerte": self._jours,
            "date": c.jour.isoformat() if c else None,
            "lieu": c.lieu if c else None,
        }
