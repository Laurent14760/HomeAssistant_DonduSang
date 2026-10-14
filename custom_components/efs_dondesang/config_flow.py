"""Assistant de configuration (config flow) et options flow."""
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
    SOURCE_HOME,
    SOURCE_POSTAL,
)

POSTAL_RE = re.compile(r"^\d{5}$")


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
                    options=DON_TYPES,
                    translation_key=CONF_DON_TYPE,
                    mode=SelectSelectorMode.LIST,
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


class EfsConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._title = "EFS"
        self._communes: list[dict[str, Any]] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=["home", "postal_code"])

    async def async_step_home(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        lat, lon = self.hass.config.latitude, self.hass.config.longitude
        if lat is None or lon is None:
            return self.async_abort(reason="no_home_location")
        self._data = {CONF_SOURCE: SOURCE_HOME, CONF_LATITUDE: lat, CONF_LONGITUDE: lon}
        self._title = f"EFS {self.hass.config.location_name or 'Maison'}"
        return await self._async_set_location()

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
                        self._data = {CONF_SOURCE: SOURCE_POSTAL, CONF_POSTAL_CODE: code}
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
            description_placeholders={"code_postal": self._data[CONF_POSTAL_CODE]},
        )

    async def _async_select_commune(self, commune: dict[str, Any]) -> ConfigFlowResult:
        self._data.update(
            {
                CONF_COMMUNE: commune["nom"],
                CONF_INSEE: commune["code"],
                CONF_LATITUDE: commune["latitude"],
                CONF_LONGITUDE: commune["longitude"],
            }
        )
        self._title = f"EFS {commune['nom']}"
        return await self._async_set_location()

    async def _async_set_location(self) -> ConfigFlowResult:
        await self.async_set_unique_id(
            f"{self._data[CONF_LATITUDE]:.3f}_{self._data[CONF_LONGITUDE]:.3f}"
        )
        self._abort_if_unique_id_configured()
        return await self.async_step_settings()

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=self._title, data=self._data, options=_clean(user_input)
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


class EfsOptionsFlow(OptionsFlow):
    """Modification des réglages sans réinstaller (rechargement automatique)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=_clean(user_input))
        return self.async_show_form(
            step_id="init", data_schema=_settings_schema(dict(self.config_entry.options))
        )
