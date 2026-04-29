"""The time platform for rainbird."""

from __future__ import annotations

import datetime
import logging

from pyrainbird.exceptions import RainbirdApiException

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import RainbirdScheduleUpdateCoordinator, RainbirdUpdateCoordinator
from .types import RainbirdConfigEntry

_LOGGER = logging.getLogger(__name__)

# Each program has 4 start time slots; unused slots are 0xFFFF.
_START_TIME_SLOTS = 4


async def _set_program_start_times(
    controller,
    program_num: int,
    times: list[datetime.time | None],
) -> None:
    """Send SetSchedule (0x21, subcmd 0x60|program) to set start times.

    Format: 21 [006N 2B] [slot0 2B] [slot1 2B] [slot2 2B] [slot3 2B]
    Slots are minutes-since-midnight; 0xFFFF means unused.
    """
    data = "21%04X" % (0x60 | program_num)
    for t in times:
        if t is None:
            data += "FFFF"
        else:
            data += "%04X" % (t.hour * 60 + t.minute)
    length = 3 + _START_TIME_SLOTS * 2  # cmd(1) + subcmd(2) + 4 slots × 2 bytes
    await controller._tunnelSip(data, length)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: RainbirdConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up entry for Rain Bird time platform."""
    data = config_entry.runtime_data
    max_programs = data.model_info.model_info.max_programs
    if not max_programs:
        return
    async_add_entities(
        RainBirdProgramStartTimeEntity(
            data.schedule_coordinator,
            data.coordinator,
            program_num,
        )
        for program_num in range(max_programs)
    )


class RainBirdProgramStartTimeEntity(
    CoordinatorEntity[RainbirdScheduleUpdateCoordinator], TimeEntity
):
    """Time entity for reading and setting a program's first start time."""

    _attr_has_entity_name = True
    _attr_translation_key = "start_time"
    _attr_icon = "mdi:clock-start"

    def __init__(
        self,
        schedule_coordinator: RainbirdScheduleUpdateCoordinator,
        update_coordinator: RainbirdUpdateCoordinator,
        program_num: int,
    ) -> None:
        """Initialize the start time entity."""
        super().__init__(schedule_coordinator)
        self._program_num = program_num
        self._controller = update_coordinator.controller
        self._attr_unique_id = (
            f"{update_coordinator.unique_id}-program-{program_num}-start-time"
        )
        self._attr_device_info = update_coordinator.program_device_info(program_num)

    async def async_added_to_hass(self) -> None:
        """Trigger a schedule refresh when added to hass."""
        await super().async_added_to_hass()
        self.coordinator.config_entry.async_create_background_task(
            self.hass,
            self.coordinator.async_request_refresh(),
            f"rainbird.program-{self._program_num}-start-time-refresh",
        )

    @property
    def native_value(self) -> datetime.time | None:
        """Return the first start time for this program."""
        schedule = self.coordinator.data
        if not schedule:
            return None
        for program in schedule.programs:
            if program.program == self._program_num:
                return program.starts[0] if program.starts else None
        return None

    async def async_set_value(self, value: datetime.time) -> None:
        """Set the first start time, preserving any additional slots."""
        times: list[datetime.time | None] = [None] * _START_TIME_SLOTS
        times[0] = value

        # Preserve existing slots 1-3 if present.
        schedule = self.coordinator.data
        if schedule:
            for program in schedule.programs:
                if program.program == self._program_num:
                    for i, t in enumerate(program.starts[1:_START_TIME_SLOTS], 1):
                        times[i] = t
                    break

        try:
            await _set_program_start_times(self._controller, self._program_num, times)
        except RainbirdApiException as err:
            raise HomeAssistantError("Rain Bird device failure") from err

        await self.coordinator.async_request_refresh()
