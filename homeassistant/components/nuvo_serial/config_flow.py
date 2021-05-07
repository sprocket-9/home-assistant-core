"""Config flow for Nuvo multi-zone amplifier integration."""
from __future__ import annotations

import logging
from typing import Any

from nuvo_serial import get_nuvo_async
from nuvo_serial.const import ranges
from nuvo_serial.exceptions import ModelMismatchError
from nuvo_serial.grand_concerto_essentia_g import SourceConfiguration, ZoneConfiguration
from serial import SerialException
import voluptuous as vol

from homeassistant.config_entries import (
    CONN_CLASS_LOCAL_POLL,
    ConfigEntry,
    ConfigFlow,
    OptionsFlow,
)
from homeassistant.const import CONF_PORT, CONF_TYPE
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow

from .const import CONF_SOURCES, CONF_ZONES, DOMAIN

_LOGGER = logging.getLogger(__name__)

models = {" ".join(model.split("_")): model for model in ranges.keys()}
DATA_SCHEMA = vol.Schema(
    {vol.Required(CONF_PORT): str, vol.Required(CONF_TYPE): vol.In(models.keys())}
)


@callback
def _idx_from_config(data: dict[str, str]) -> dict[int, str]:
    """Cleanse input from user."""
    modded = {}

    for k, v in data.items():
        modded[int(k.split("_")[1])] = v.strip()

    return modded


@callback
def _get_source_schema(
    sources: dict[str, str] | list[SourceConfiguration]
) -> vol.Schema:
    """Create schema for source validation."""
    if isinstance(sources, dict):
        data_schema = vol.Schema(
            {
                vol.Optional(f"source_{source}", default=name): str
                for source, name in sources.items()
            }
        )
    else:
        data_schema = vol.Schema(
            {
                vol.Optional(f"source_{source.source}", default=source.name): str
                for source in sources
            }
        )
    return data_schema


class NuvoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Nuvo Amplifier."""

    VERSION = 1
    CONNECTION_CLASS = CONN_CLASS_LOCAL_POLL

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> NuvoOptionsFlowHandler:
        """Define the config flow to handle options."""
        return NuvoOptionsFlowHandler(config_entry)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle the initial step."""

        self._data: dict[str, Any] = {}
        errors: dict[str, str] = {}

        if user_input is not None:
            if self._port_already_in_use(user_input[CONF_PORT]):
                raise AbortFlow("port_in_use")

            try:
                self._nuvo = await get_nuvo_async(
                    user_input[CONF_PORT], models[user_input[CONF_TYPE]]
                )
            except SerialException:
                _LOGGER.exception("")
                errors[CONF_PORT] = "port"
            except ModelMismatchError:
                _LOGGER.exception("")
                raise AbortFlow("model")
            except Exception:
                _LOGGER.exception("")
                errors["base"] = "cannot_connect"
            else:

                self._data[CONF_PORT] = user_input[CONF_PORT]
                self._data[CONF_TYPE] = models[user_input[CONF_TYPE]]
                return await self.async_step_sources()

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    @callback
    def _port_already_in_use(self, port: str) -> bool:
        """Check the port is not already in use."""

        in_use = False

        for existing_nuvo in self.hass.config_entries.async_entries(DOMAIN):
            if existing_nuvo.data.get(CONF_PORT, "") == port:
                in_use = True
                break

        return in_use

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle the initial step."""
        return await self.async_step_init(user_input)

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle Nuvo sources."""

        errors: dict[str, str] = {}

        if user_input is not None:
            """process sources"""
            self._data[CONF_SOURCES] = _idx_from_config(user_input)
            return await self.async_step_zones()

        try:
            sources = await self._get_nuvo_sources()
        except Exception:
            _LOGGER.exception("")
            await self._async_nuvo_disconnect()
            raise AbortFlow("sources")

        source_schema = _get_source_schema(sources)
        return self.async_show_form(
            step_id="sources",
            data_schema=source_schema,
            errors=errors,
        )

    async def async_step_zones(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle Nuvo zones."""

        errors: dict[str, str] = {}

        if user_input is not None:
            """process zones"""
            self._data[CONF_ZONES] = _idx_from_config(user_input)
            return await self._create_entry()

        try:
            zones = await self._get_nuvo_zones()
        except Exception:
            _LOGGER.exception("")
            await self._async_nuvo_disconnect()
            raise AbortFlow("zones")

        zone_schema = self._get_zone_schema(zones)
        return self.async_show_form(
            step_id="zones",
            data_schema=zone_schema,
            errors=errors,
        )

    async def _create_entry(self) -> dict[str, Any]:
        """Create device and entities."""
        await self._async_nuvo_disconnect()
        self._nuvo = None
        title = " ".join(self._data[CONF_TYPE].split("_"))
        return self.async_create_entry(title=title, data=self._data)

    @callback
    def _get_zone_schema(self, zones: list[ZoneConfiguration]) -> vol.Schema:
        """Create schema for zone validation."""
        data_schema = vol.Schema(
            {
                vol.Optional(f"zone_{zone.zone}", default=zone.name): str
                for zone in zones
            }
        )
        return data_schema

    async def _get_nuvo_sources(self) -> list[SourceConfiguration]:
        """Retrieve enabled sources from Nuvo."""
        source_count = ranges[self._data[CONF_TYPE]]["sources"]
        sources = []
        for source_num in range(1, source_count + 1):
            source = await self._nuvo.source_status(source_num)
            if source.enabled:
                sources.append(source)

        return sources

    async def _get_nuvo_zones(self) -> list[ZoneConfiguration]:
        """Retrieve enabled zones from Nuvo."""
        zone_count = ranges[self._data[CONF_TYPE]]["zones"]["physical"]
        zones = []
        for zone_num in range(1, zone_count + 1):
            zone = await self._nuvo.zone_configuration(zone_num)
            if zone.enabled:
                zones.append(zone)

        return zones

    async def _async_nuvo_disconnect(self):
        """Disconnect from the amplifier."""
        await self._nuvo.disconnect()


class NuvoOptionsFlowHandler(OptionsFlow):
    """Handle a Nuvo options flow."""

    def __init__(self, config_entry: ConfigEntry):
        """Initialize."""
        self.config_entry = config_entry
        self._data: dict[str, Any] = {}
        self._port_changed = False

    @callback
    def _previous_sources(self) -> dict[str, str]:
        """Get current sources."""
        previous: dict[str, str]
        if CONF_SOURCES in self.config_entry.options:
            previous = self.config_entry.options[CONF_SOURCES]
        else:
            previous = self.config_entry.data[CONF_SOURCES]

        return previous

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Manage the options."""
        return await self.async_step_port()

    async def async_step_port(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle serial port change."""

        current_port = self.config_entry.data[CONF_PORT]
        errors: dict[str, str] = {}

        if user_input is not None:
            _LOGGER.debug(user_input[CONF_PORT])
            if user_input[CONF_PORT] != current_port:
                self._port_changed = True
            self._data[CONF_PORT] = user_input[CONF_PORT]
            return await self.async_step_sources()

        schema = vol.Schema({vol.Required(CONF_PORT, default=current_port): str})
        return self.async_show_form(step_id="port", data_schema=schema, errors=errors)

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle Source changes."""
        if user_input is not None:
            _LOGGER.debug("in aync_step_source abt to async_create_entry")
            _LOGGER.debug(self._data[CONF_PORT])
            self._data[CONF_SOURCES] = _idx_from_config(user_input)
            return self.async_create_entry(title="", data=self._data)

        previous_sources = self._previous_sources()
        source_schema = _get_source_schema(previous_sources)
        return self.async_show_form(step_id="sources", data_schema=source_schema)
