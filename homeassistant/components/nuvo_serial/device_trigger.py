"""Provides device triggers for Nuvo multi-zone amplifier (serial)."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_PLATFORM,
    CONF_TYPE,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from . import DOMAIN
from .const import (
    DOMAIN_EVENT,
    EVENT_DEVICE_RESTARTED,
    EVENT_KEYPAD_NEXT,
    EVENT_KEYPAD_PLAY_PAUSE,
    EVENT_KEYPAD_PREV,
    ZONE,
)

SYSTEM_TRIGGER_TYPES = {EVENT_DEVICE_RESTARTED}
ZONE_TRIGGER_TYPES = {EVENT_KEYPAD_PLAY_PAUSE, EVENT_KEYPAD_PREV, EVENT_KEYPAD_NEXT}
TRIGGER_TYPES = SYSTEM_TRIGGER_TYPES.union(ZONE_TRIGGER_TYPES)

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Optional(CONF_ENTITY_ID): cv.entity_id,
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
    }
)


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """List device triggers for Nuvo multi-zone amplifier (serial) devices."""

    registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get(device_id)
    triggers: list[dict[str, str]] = []

    if not device_entry:
        return triggers

    if device_entry.model == ZONE.capitalize():
        for entry in er.async_entries_for_device(registry, device_id):
            if entry.platform != DOMAIN or entry.domain != "media_player":
                continue

            for trigger_type in ZONE_TRIGGER_TYPES:
                triggers.append(
                    {
                        CONF_PLATFORM: "device",
                        CONF_DEVICE_ID: device_id,
                        CONF_DOMAIN: DOMAIN,
                        CONF_ENTITY_ID: entry.entity_id,
                        CONF_TYPE: trigger_type,
                    }
                )

    if device_entry.via_device_id is None:
        for trigger_type in SYSTEM_TRIGGER_TYPES:
            triggers.append(
                {
                    CONF_PLATFORM: "device",
                    CONF_DEVICE_ID: device_id,
                    CONF_DOMAIN: DOMAIN,
                    CONF_TYPE: trigger_type,
                }
            )

    return triggers


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a trigger."""

    event_data = {
        CONF_TYPE: config[CONF_TYPE],
    }
    if entity_id := config.get(CONF_ENTITY_ID):
        event_data[CONF_ENTITY_ID] = entity_id
    else:
        event_data[CONF_DEVICE_ID] = config[CONF_DEVICE_ID]

    event_config = event_trigger.TRIGGER_SCHEMA(
        {
            event_trigger.CONF_PLATFORM: "event",
            event_trigger.CONF_EVENT_TYPE: DOMAIN_EVENT,
            event_trigger.CONF_EVENT_DATA: event_data,
        }
    )

    return await event_trigger.async_attach_trigger(
        hass, event_config, action, trigger_info, platform_type="device"
    )
