"""Capteurs : prochaine collecte, places, taux de remplissage, collectes à venir."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EfsConfigEntry
from .const import CONF_DON_TYPE, CONF_MAISONS_DU_DON, CONF_MAX_ITEMS
from .entity import EfsEntity

UNIT_PLACES = "places"


async def async_setup_entry(
    hass: HomeAssistant, entry: EfsConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            ProchaineCollecteSensor(coordinator),
            PlacesTotalesSensor(coordinator),
            PlacesRestantesSensor(coordinator),
            TauxRemplissageSensor(coordinator),
            CollectesAVenirSensor(coordinator),
        ]
    )


class ProchaineCollecteSensor(EfsEntity, SensorEntity):
    """Date et heure de début de la prochaine collecte."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:water-plus"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "prochaine_collecte", "sensor")

    @property
    def native_value(self) -> datetime | None:
        c = self.prochaine
        return c.debut if c else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        attrs: dict[str, Any] = {
            "type_don": self.coordinator.options[CONF_DON_TYPE],
            "api_disponible": data.api_disponible if data else False,
            "derniere_mise_a_jour": data.derniere_reussite.isoformat()
            if data and data.derniere_reussite
            else None,
        }
        c = self.prochaine
        if c is None:
            return attrs
        attrs.update(
            {
                "lieu": c.lieu,
                "adresse": c.adresse,
                "commune": c.commune,
                "code_postal": c.code_postal,
                "distance": c.distance_km,
                "fin": c.fin.isoformat(),
                "horaires": c.horaires,
                "creneaux": [cr.libelle for cr in c.creneaux],
                "statut": c.statut,
                "places_totales": c.places_totales,
                "places_restantes": c.places_restantes,
                "places_reservees": c.places_reservees,
                "taux_remplissage": c.taux_remplissage,
                "places": c.texte_places,
                "lien_rdv": c.lien_rdv,
                "libelle": c.libelle_court,
                "nature": c.nature,
                "latitude": c.latitude,
                "longitude": c.longitude,
            }
        )
        return attrs


class _PlacesBase(EfsEntity, SensorEntity):
    """Base des capteurs numériques : None (unknown) tant que le planning n'est pas ouvert."""

    _attr_native_unit_of_measurement = UNIT_PLACES
    _attr_icon = "mdi:seat"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        c = self.prochaine
        return {
            "lieu": c.lieu if c else None,
            "date": c.jour.isoformat() if c else None,
            "statut": c.statut if c else None,
        }


class PlacesTotalesSensor(_PlacesBase):
    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "prochaine_collecte_places_totales", "sensor")

    @property
    def native_value(self) -> int | None:
        c = self.prochaine
        return c.places_totales if c else None


class PlacesRestantesSensor(_PlacesBase):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:seat-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "prochaine_collecte_places_restantes", "sensor")

    @property
    def native_value(self) -> int | None:
        c = self.prochaine
        return c.places_restantes if c else None


class TauxRemplissageSensor(_PlacesBase):
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:gauge"
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "prochaine_collecte_taux_remplissage", "sensor")

    @property
    def native_value(self) -> float | None:
        c = self.prochaine
        return c.taux_remplissage if c else None


class CollectesAVenirSensor(EfsEntity, SensorEntity):
    """Nombre de collectes dans l'horizon, et liste compacte des N prochaines."""

    _attr_icon = "mdi:calendar-heart"
    _attr_native_unit_of_measurement = "collectes"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "collectes_a_venir", "sensor")

    @property
    def native_value(self) -> int:
        return len(self.collectes)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        n = int(self.coordinator.options[CONF_MAX_ITEMS])
        attrs: dict[str, Any] = {
            "collectes": [c.as_compact() for c in self.collectes[:n]],
        }
        data = self.coordinator.data
        if self.coordinator.options[CONF_MAISONS_DU_DON] and data:
            attrs["maisons_du_don"] = [m.as_dict() for m in data.result.maisons_du_don[:5]]
        return attrs
