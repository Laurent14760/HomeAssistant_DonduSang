"""Assistant d'installation (config flow) et « Configurer » (options flow).

La localisation se choisit à l'installation puis se modifie à tout moment via
Paramètres → Appareils et services → EFS → Configurer → Localisation, sans réinstaller.
"""
from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import EfsApiError, async_search_communes
from .const import (
    CONF_ALERT_DAYS,
    CONF_COMMUNE,
    CONF_DON_TYPE,
    CONF_ENTITY,
    CONF_HORIZON,
    CONF_INCLUDE_PRO,
    CONF_INSEE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MAISONS_DU_DON,
    CONF_MAX_ITEMS,
    CONF_POSTAL_CODE,
    CONF_RADIUS,
    CONF_SCAN_INTERVAL,
    CONF_SOURCE,
    DEFAULT_OPTIONS,
    DOMAIN,
    DON_TYPES,
    MAX_ITEMS_LIMIT,
    MIN_SCAN_INTERVAL,
    SOURCE_ENTITY,
    SOURCE_HOME,
    SOURCE_POSTAL,
)
from .location import coords_from_attributes, describe, entity_label, same_location, unique_id_for

POSTAL_RE = re.compile(r"^\d{5}$")
TRACKABLE_DOMAINS = ["zone", "person", "device_tracker"]
LOCATION_MENU = ["home", "postal_code", "entity"]


def _number(minimum: int, maximum: int, unit: str, step: int = 1) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum, max=maximum, step=step, unit_of_measurement=unit,
            mode=NumberSelectorMode.BOX,
        )
    )


def _settings_schema(values: dict[str, Any]) -> vol.Schema:
    v = {**DEFAULT_OPTIONS, **values}
    return vol.Schema(
        {
            vol.Required(CONF_RADIUS, default=v[CONF_RADIUS]): _number(1, 50, "km"),
            vol.Required(CONF_DON_TYPE, default=v[CONF_DON_TYPE]): SelectSelector(
                SelectSelectorConfig(
                    options=DON_TYPES, translation_key=CONF_DON_TYPE, mode=SelectSelectorMode.LIST
                )
            ),
            vol.Required(CONF_INCLUDE_PRO, default=v[CONF_INCLUDE_PRO]): BooleanSelector(),
            vol.Required(CONF_HORIZON, default=v[CONF_HORIZON]): _number(1, 180, "j"),
            vol.Required(CONF_MAX_ITEMS, default=v[CONF_MAX_ITEMS]): _number(1, MAX_ITEMS_LIMIT, ""),
            vol.Required(CONF_SCAN_INTERVAL, default=v[CONF_SCAN_INTERVAL]): _number(
                MIN_SCAN_INTERVAL, 1440, "min", 5
            ),
            vol.Required(CONF_ALERT_DAYS, default=v[CONF_ALERT_DAYS]): _number(1, 60, "j"),
            vol.Required(CONF_MAISONS_DU_DON, default=v[CONF_MAISONS_DU_DON]): BooleanSelector(),
        }
    )


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    """Les NumberSelector renvoient des float : on remet des entiers."""
    out = dict(user_input)
    for key in (CONF_RADIUS, CONF_HORIZON, CONF_MAX_ITEMS, CONF_SCAN_INTERVAL, CONF_ALERT_DAYS):
        out[key] = int(out[key])
    return out


class _LocationSteps:
    """Étapes de choix du lieu, communes à l'installation et à « Configurer »."""

    _loc: dict[str, Any]
    _title: str
    _communes: list[dict[str, Any]]

    async def _async_location_done(self) -> ConfigFlowResult:  # pragma: no cover - abstrait
        raise NotImplementedError

    async def async_step_home(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self.hass.config.latitude is None or self.hass.config.longitude is None:
            return self.async_abort(reason="no_home_location")
        self._loc = {CONF_SOURCE: SOURCE_HOME}
        self._title = f"EFS {self.hass.config.location_name or 'Maison'}"
        return await self._async_location_done()

    async def async_step_postal_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            code = user_input[CONF_POSTAL_CODE].strip()
            if not POSTAL_RE.match(code):
                errors[CONF_POSTAL_CODE] = "invalid_postal_code"
            else:
                try:
                    self._communes = await async_search_communes(
                        async_get_clientsession(self.hass), code
                    )
                except EfsApiError:
                    errors["base"] = "cannot_connect"
                else:
                    if not self._communes:
                        errors[CONF_POSTAL_CODE] = "unknown_postal_code"
                    else:
                        self._loc = {CONF_SOURCE: SOURCE_POSTAL, CONF_POSTAL_CODE: code}
                        if len(self._communes) == 1:
                            return await self._async_select_commune(self._communes[0])
                        return await self.async_step_commune()
        return self.async_show_form(
            step_id="postal_code",
            data_schema=vol.Schema({vol.Required(CONF_POSTAL_CODE): str}),
            errors=errors,
        )

    async def async_step_commune(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            commune = next(c for c in self._communes if c["code"] == user_input[CONF_INSEE])
            return await self._async_select_commune(commune)
        options = [SelectOptionDict(value=c["code"], label=c["nom"]) for c in self._communes]
        return self.async_show_form(
            step_id="commune",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_INSEE): SelectSelector(
                        SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST)
                    )
                }
            ),
            description_placeholders={"code_postal": self._loc[CONF_POSTAL_CODE]},
        )

    async def _async_select_commune(self, commune: dict[str, Any]) -> ConfigFlowResult:
        self._loc.update(
            {
                CONF_COMMUNE: commune["nom"],
                CONF_INSEE: commune["code"],
                CONF_LATITUDE: commune["latitude"],
                CONF_LONGITUDE: commune["longitude"],
            }
        )
        self._title = f"EFS {commune['nom']}"
        return await self._async_location_done()

    async def async_step_entity(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            entity_id = user_input[CONF_ENTITY]
            state = self.hass.states.get(entity_id)
            if state is None or coords_from_attributes(state.attributes) is None:
                errors[CONF_ENTITY] = "entity_no_location"
            else:
                self._loc = {CONF_SOURCE: SOURCE_ENTITY, CONF_ENTITY: entity_id}
                label = entity_label(entity_id, state.name, self.hass.config.location_name)
                self._title = f"EFS {label}"
                return await self._async_location_done()
        return self.async_show_form(
            step_id="entity",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ENTITY): EntitySelector(
                        EntitySelectorConfig(domain=TRACKABLE_DOMAINS)
                    )
                }
            ),
            errors=errors,
        )


class EfsConfigFlow(_LocationSteps, ConfigFlow, domain=DOMAIN):
    """Installation : une instance par lieu, autant d'instances que souhaité."""

    VERSION = 1

    def __init__(self) -> None:
        self._loc = {}
        self._title = "EFS"
        self._communes = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=LOCATION_MENU)

    async def _async_location_done(self) -> ConfigFlowResult:
        await self.async_set_unique_id(unique_id_for(self._loc))
        self._abort_if_unique_id_configured()
        for other in self.hass.config_entries.async_entries(DOMAIN):
            if same_location(other.data, self._loc):
                return self.async_abort(reason="already_configured")
        return await self.async_step_settings()

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=self._title, data=self._loc, options=_clean(user_input)
            )
        return self.async_show_form(
            step_id="settings",
            data_schema=_settings_schema({}),
            description_placeholders={"lieu": self._title},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EfsOptionsFlow()


class EfsOptionsFlow(_LocationSteps, OptionsFlow):
    """« Configurer » : changer de lieu ou ajuster les réglages, sans réinstaller."""

    def __init__(self) -> None:
        self._loc = {}
        self._title = ""
        self._communes = []

    def _current_location(self) -> str:
        data = self.config_entry.data
        name = None
        if data.get(CONF_SOURCE) == SOURCE_ENTITY:
            entity_id = data.get(CONF_ENTITY, "")
            state = self.hass.states.get(entity_id)
            name = entity_label(entity_id, state.name if state else None, self.hass.config.location_name)
        return describe(data, name)

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["location", "settings"],
            description_placeholders={"lieu": self._current_location()},
        )

    async def async_step_location(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="location",
            menu_options=LOCATION_MENU,
            description_placeholders={"lieu": self._current_location()},
        )

    async def _async_location_done(self) -> ConfigFlowResult:
        entry = self.config_entry
        new_uid = unique_id_for(self._loc)
        for other in self.hass.config_entries.async_entries(DOMAIN):
            if other.entry_id != entry.entry_id and (
                other.unique_id == new_uid or same_location(other.data, self._loc)
            ):
                return self.async_abort(reason="already_configured")
        # Le titre suit le lieu ; les identifiants d'entités ne changent pas,
        # les tableaux de bord et automatisations existants restent valides.
        self.hass.config_entries.async_update_entry(
            entry, data=self._loc, title=self._title, unique_id=new_uid
        )
        return self.async_create_entry(data=dict(entry.options))

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=_clean(user_input))
        return self.async_show_form(
            step_id="settings", data_schema=_settings_schema(dict(self.config_entry.options))
        )
