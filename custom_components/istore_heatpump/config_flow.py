from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from .const import (DOMAIN, CONF_USERNAME, CONF_PASSWORD, CONF_ACCESS_TOKEN, CONF_PARENT_ID, CONF_MDM_ID)
from .api import authenticate

_LOGGER = logging.getLogger(__name__)


class CannotConnect(HomeAssistantError):
    """Error raised when API connection fails."""


class InvalidAuth(HomeAssistantError):
    """Error for invalid authentication."""


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            try:
                creds = await authenticate(username, password)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception as exc:
                _LOGGER.error("iStore config flow error: %s", exc)
                msg = str(exc).lower()
                if "login failed" in msg or "invalid" in msg or "401" in msg:
                    errors["base"] = "invalid_auth"
                else:
                    errors["base"] = "cannot_connect"
            else:
                # Successfully authenticated and retrieved discovered IDs
                return self.async_create_entry(
                    title="iStore Heat Pump",
                    data={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_ACCESS_TOKEN: creds["access_token"],
                        CONF_PARENT_ID: creds["parent_id"],
                        CONF_MDM_ID: creds["mdm_id"],
                    },
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for iStore Heat Pump."""

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            cold_water_temp = user_input["cold_water_temp"]
            shower_flow_rate = user_input["shower_flow_rate"]
            shower_temp = user_input["shower_temp"]
            tempering_temp = user_input["tempering_temp"]

            try:
                creds = await authenticate(username, password)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception as exc:
                _LOGGER.error("iStore options flow error: %s", exc)
                msg = str(exc).lower()
                if "login failed" in msg or "invalid" in msg or "401" in msg:
                    errors["base"] = "invalid_auth"
                else:
                    errors["base"] = "cannot_connect"
            else:
                options_dict = {
                    "cold_water_temp": cold_water_temp,
                    "shower_flow_rate": shower_flow_rate,
                    "shower_temp": shower_temp,
                    "tempering_temp": tempering_temp,
                }
                # Update config entry data directly and save custom options
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_ACCESS_TOKEN: creds["access_token"],
                        CONF_PARENT_ID: creds["parent_id"],
                        CONF_MDM_ID: creds["mdm_id"],
                    },
                    options=options_dict,
                )
                return self.async_create_entry(title="", data=options_dict)

        # Pre-populate with current values from config_entry.data and options
        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=self.config_entry.data.get(CONF_USERNAME, "")): str,
                vol.Required(CONF_PASSWORD, default=self.config_entry.data.get(CONF_PASSWORD, "")): str,
                vol.Required("cold_water_temp", default=self.config_entry.options.get("cold_water_temp", 15)): vol.Coerce(int),
                vol.Required("shower_flow_rate", default=self.config_entry.options.get("shower_flow_rate", 9.0)): vol.Coerce(float),
                vol.Required("shower_temp", default=self.config_entry.options.get("shower_temp", 40)): vol.Coerce(int),
                vol.Required("tempering_temp", default=self.config_entry.options.get("tempering_temp", 50)): vol.Coerce(int),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            errors=errors,
        )
