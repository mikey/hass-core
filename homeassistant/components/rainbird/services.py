"""Rain Bird Irrigation system services."""

from __future__ import annotations

import logging

import voluptuous as vol

from pyrainbird.exceptions import RainbirdApiException, RainbirdDeviceBusyException

from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import ATTR_CONFIG_ENTRY_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, service
from homeassistant.helpers.selector import ConfigEntrySelector
from homeassistant.helpers.typing import VolDictType

from .const import ATTR_DURATION, ATTR_PROGRAM, DOMAIN
from .types import RainbirdConfigEntry

_LOGGER = logging.getLogger(__name__)

SERVICE_START_IRRIGATION = "start_irrigation"
SERVICE_RUN_PROGRAM = "run_program"

SERVICE_SCHEMA_IRRIGATION: VolDictType = {
    vol.Required(ATTR_DURATION): cv.positive_float,
}

SERVICE_SCHEMA_RUN_PROGRAM: VolDictType = {
    vol.Required(ATTR_CONFIG_ENTRY_ID): ConfigEntrySelector({"integration": DOMAIN}),
    vol.Required(ATTR_PROGRAM): vol.All(vol.Coerce(int), vol.Range(min=1, max=8)),
}


async def _async_run_program(call: ServiceCall) -> None:
    """Run a Rain Bird irrigation program."""
    entry: RainbirdConfigEntry = service.async_get_config_entry(  # type: ignore[assignment]
        call.hass, DOMAIN, call.data[ATTR_CONFIG_ENTRY_ID]
    )

    # Program number is 1-based from the user, 0-based for the API.
    program = call.data[ATTR_PROGRAM] - 1
    controller = entry.runtime_data.controller
    try:
        await controller.set_program(program)
    except RainbirdDeviceBusyException as err:
        raise HomeAssistantError(
            "Rain Bird device is busy; Wait and try again"
        ) from err
    except RainbirdApiException as err:
        raise HomeAssistantError("Rain Bird device failure") from err

    # Trigger a refresh to pick up the new state.
    await entry.runtime_data.coordinator.async_request_refresh()


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services."""

    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_START_IRRIGATION,
        entity_domain=SWITCH_DOMAIN,
        schema=SERVICE_SCHEMA_IRRIGATION,
        func="async_turn_on",
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_RUN_PROGRAM,
        _async_run_program,
        schema=vol.Schema(SERVICE_SCHEMA_RUN_PROGRAM),
    )
