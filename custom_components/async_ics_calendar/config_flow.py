"""Config flow for Async ICS Calendar: add, reconfigure and tune calendars in the UI."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME, CONF_URL
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_DAYS_BACKWARD,
    CONF_DAYS_FORWARD,
    CONF_REFRESH_MINUTES,
    DEFAULT_DAYS_BACKWARD,
    DEFAULT_DAYS_FORWARD,
    DEFAULT_NAME,
    DEFAULT_REFRESH_MINUTES,
    DOMAIN,
)
from .coordinator import async_validate, url_hash

CALENDAR_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): TextSelector(),
        vol.Required(CONF_URL): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
    }
)


def _number(minimum: int, maximum: int, unit: str) -> vol.All:
    return vol.All(
        NumberSelector(
            NumberSelectorConfig(
                min=minimum,
                max=maximum,
                step=1,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement=unit,
            )
        ),
        vol.Coerce(int),
    )


OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REFRESH_MINUTES): _number(1, 1440, "min"),
        vol.Required(CONF_DAYS_BACKWARD): _number(0, 365, "d"),
        vol.Required(CONF_DAYS_FORWARD): _number(1, 730, "d"),
    }
)

DEFAULT_OPTIONS = {
    CONF_REFRESH_MINUTES: DEFAULT_REFRESH_MINUTES,
    CONF_DAYS_BACKWARD: DEFAULT_DAYS_BACKWARD,
    CONF_DAYS_FORWARD: DEFAULT_DAYS_FORWARD,
}


class AsyncIcsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add an ICS calendar."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> AsyncIcsOptionsFlow:
        """Refresh interval and event window."""
        return AsyncIcsOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Name and URL of a new calendar."""
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].strip()
            await self.async_set_unique_id(url_hash(url))
            self._abort_if_unique_id_configured()
            if error := await async_validate(self.hass, url):
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={CONF_URL: url, CONF_NAME: user_input[CONF_NAME]},
                    options=DEFAULT_OPTIONS,
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(CALENDAR_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Take over a calendar from YAML, settings included."""
        url = import_data[CONF_URL]
        await self.async_set_unique_id(url_hash(url))
        self._abort_if_unique_id_configured()
        # No check of the feed here: it worked from YAML, and the entry retries
        # by itself while the feed is unreachable.
        return self.async_create_entry(
            title=import_data[CONF_NAME],
            data={CONF_URL: url, CONF_NAME: import_data[CONF_NAME]},
            options={key: import_data[key] for key in DEFAULT_OPTIONS},
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the name or URL of a calendar; its entity stays the same."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].strip()
            if any(
                other.entry_id != entry.entry_id and other.data.get(CONF_URL) == url
                for other in self._async_current_entries(include_ignore=False)
            ):
                errors["base"] = "already_configured"
            elif error := await async_validate(self.hass, url):
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    title=user_input[CONF_NAME],
                    data={CONF_URL: url, CONF_NAME: user_input[CONF_NAME]},
                )
        current = user_input or {
            CONF_NAME: entry.data.get(CONF_NAME, entry.title),
            CONF_URL: entry.data[CONF_URL],
        }
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(CALENDAR_SCHEMA, current),
            errors=errors,
        )


class AsyncIcsOptionsFlow(OptionsFlow):
    """Refresh interval and event window of a calendar."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = {**DEFAULT_OPTIONS, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(OPTIONS_SCHEMA, current),
        )
