"""Intégration Home Assistant des collectes de l'Établissement français du sang."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, STORAGE_VERSION
from .coordinator import EfsCoordinator
from .services import async_setup_services

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.CALENDAR, Platform.BINARY_SENSOR]

# Configuration 100 % interface : aucune clé YAML n'est attendue.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type EfsConfigEntry = ConfigEntry[EfsCoordinator]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Déclare l'action de recherche à la demande (utilisée par la carte Lovelace)."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: EfsConfigEntry) -> bool:
    coordinator = EfsCoordinator(hass, entry)
    await coordinator.async_load_cache()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(coordinator.async_start_tracking())
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EfsConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Supprime le cache disque lors de la suppression de l'instance."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
