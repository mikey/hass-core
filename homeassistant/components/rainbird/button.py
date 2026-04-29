"""The button platform for rainbird."""

from __future__ import annotations

import logging

from pyrainbird.exceptions import RainbirdApiException, RainbirdDeviceBusyException

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import RainbirdUpdateCoordinator
from .types import RainbirdConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: RainbirdConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up entry for Rain Bird button platform."""
    data = config_entry.runtime_data
    max_programs = data.model_info.model_info.max_programs
    if not max_programs:
        return
    async_add_entities(
        RainBirdRunProgramButton(data.coordinator, program_num)
        for program_num in range(max_programs)
    )


class RainBirdRunProgramButton(ButtonEntity):
    """Button to manually run a Rain Bird irrigation program."""

    _attr_has_entity_name = True
    _attr_translation_key = "run"
    _attr_icon = "mdi:play"

    def __init__(
        self,
        coordinator: RainbirdUpdateCoordinator,
        program_num: int,
    ) -> None:
        """Initialize the button."""
        self._coordinator = coordinator
        self._program_num = program_num
        self._attr_unique_id = (
            f"{coordinator.unique_id}-run-program-{program_num}"
        )
        self._attr_device_info = coordinator.program_device_info(program_num)

    async def async_press(self) -> None:
        """Run the program."""
        try:
            await self._coordinator.controller.set_program(self._program_num)
        except RainbirdDeviceBusyException as err:
            raise HomeAssistantError(
                "Rain Bird device is busy; Wait and try again"
            ) from err
        except RainbirdApiException as err:
            raise HomeAssistantError("Rain Bird device failure") from err
        await self._coordinator.async_request_refresh()
