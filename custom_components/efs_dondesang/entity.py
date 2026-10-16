"""Classe de base commune aux entités EFS."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, EFS_WEBSITE, MANUFACTURER
from .coordinator import EfsCoordinator
from .parser import Collecte, next_collecte


class EfsEntity(CoordinatorEntity[EfsCoordinator]):
    """Entité rattachée à l'appareil (service) d'une instance EFS."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EfsCoordinator, key: str, domain: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        # L'identifiant d'entité est dérivé du nom de l'instance (« EFS Caen » →
        # sensor.efs_caen_prochaine_collecte), ce qui distingue clairement plusieurs zones.
        # Une entité déjà enregistrée conserve son identifiant, même si le lieu change.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model="API Carto v3",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=EFS_WEBSITE,
        )

    @property
    def available(self) -> bool:
        # Données conservées en cache en cas de panne : on reste disponible.
        return self.coordinator.data is not None

    @property
    def collectes(self) -> list[Collecte]:
        return self.coordinator.data.result.collectes if self.coordinator.data else []

    @property
    def prochaine(self) -> Collecte | None:
        return next_collecte(self.collectes, dt_util.now())
