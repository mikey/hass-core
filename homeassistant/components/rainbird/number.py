"""The number platform for rainbird."""

import logging

from pyrainbird.data import WaterBudget
from pyrainbird.exceptions import RainbirdApiException, RainbirdDeviceBusyException

from homeassistant.components.number import NumberEntity
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RainbirdScheduleUpdateCoordinator, RainbirdUpdateCoordinator
from .types import RainbirdConfigEntry

_LOGGER = logging.getLogger(__name__)

# WaterBudgetSet command (0x31): command + program (1 byte) + adjust (2 bytes) = 4 bytes
# Not exposed by pyrainbird as a method, so we encode and tunnel it directly.
_WATER_BUDGET_SET_CMD = 0x31
_WATER_BUDGET_SET_LENGTH = 4

# SetSchedule command (0x21) for zone run times mirrors RetrieveSchedule (0x20).
# Format: 21 [subcmd 2B] [zone1_pgm0 2B] ... [zone1_pgmN 2B] [zone2_pgm0 2B] ... [zone2_pgmN 2B]
# Length = 3 (cmd + 2-byte subcmd) + 4 * max_programs (2 zones × programs × 2 bytes each)
_SET_SCHEDULE_CMD = 0x21
_ZONE_RUNTIME_PAGE_BASE = 0x80


async def _set_water_budget(controller, program: int, adjust: int) -> None:
    """Send the WaterBudgetSet SIP command directly via tunnelSip."""
    data = "%02X%02X%04X" % (_WATER_BUDGET_SET_CMD, program, adjust)
    await controller._tunnelSip(data, _WATER_BUDGET_SET_LENGTH)


async def _set_zone_page_durations(
    controller,
    zone_page: int,
    zone_durations: list[list[int]],
) -> None:
    """Send SetSchedule for a zone page (2 zones) via tunnelSip.

    zone_durations: [[pgm0_min, pgm1_min, ...], [pgm0_min, pgm1_min, ...]]
    """
    max_programs = len(zone_durations[0])
    data = "21%04X" % (_ZONE_RUNTIME_PAGE_BASE | zone_page)
    for zone_mins in zone_durations:
        for minutes in zone_mins:
            data += "%04X" % minutes
    length = 3 + 4 * max_programs
    await controller._tunnelSip(data, length)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: RainbirdConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up entry for a Rain Bird number platform."""
    data = config_entry.runtime_data
    coordinator = data.coordinator
    schedule_coordinator = data.schedule_coordinator

    entities: list[NumberEntity] = [RainDelayNumber(coordinator)]

    max_programs = data.model_info.model_info.max_programs

    # Water budget (seasonal adjustment) number per program.
    if max_programs and data.model_info.model_info.supports_water_budget:
        entities.extend(
            RainBirdWaterBudgetNumber(coordinator, program_num)
            for program_num in range(max_programs)
        )

    # Zone runtime numbers for each (zone, program) combination.
    if max_programs and coordinator.data.zones:
        for zone_num in sorted(coordinator.data.zones):
            for program_num in range(max_programs):
                entities.append(
                    RainBirdZoneDurationNumber(
                        schedule_coordinator,
                        coordinator,
                        zone_num,
                        program_num,
                        max_programs,
                    )
                )

    async_add_entities(entities)


class RainDelayNumber(CoordinatorEntity[RainbirdUpdateCoordinator], NumberEntity):
    """A number implementation for the rain delay."""

    _attr_native_min_value = 0
    _attr_native_max_value = 14
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_has_entity_name = True

    def __init__(self, coordinator: RainbirdUpdateCoordinator) -> None:
        """Initialize the Rain Bird sensor."""
        super().__init__(coordinator)
        if coordinator.unique_id is not None:
            self._attr_unique_id = f"{coordinator.unique_id}-rain-delay"
            self._attr_device_info = coordinator.device_info
            self._attr_name = "Rain delay"
        else:
            self._attr_name = f"{coordinator.device_name} Rain delay"

    @property
    def native_value(self) -> float | None:
        """Return the value reported by the sensor."""
        return self.coordinator.data.rain_delay

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        try:
            await self.coordinator.controller.set_rain_delay(value)
        except RainbirdDeviceBusyException as err:
            raise HomeAssistantError(
                "Rain Bird device is busy; Wait and try again"
            ) from err
        except RainbirdApiException as err:
            raise HomeAssistantError("Rain Bird device failure") from err


class RainBirdWaterBudgetNumber(
    CoordinatorEntity[RainbirdUpdateCoordinator], NumberEntity
):
    """Number entity to read and set the water budget (seasonal adjustment) per program."""

    _attr_native_min_value = 0
    _attr_native_max_value = 200
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:water-percent"
    _attr_has_entity_name = True
    _attr_translation_key = "water_budget"

    def __init__(
        self, coordinator: RainbirdUpdateCoordinator, program_num: int
    ) -> None:
        """Initialize the water budget number."""
        super().__init__(coordinator)
        self._program_num = program_num
        self._attr_unique_id = (
            f"{coordinator.unique_id}-water-budget-number-{program_num}"
        )
        self._attr_device_info = coordinator.program_device_info(program_num)

    @property
    def native_value(self) -> float | None:
        """Return the current water budget percentage."""
        budgets = self.coordinator.data.water_budgets
        if budgets and self._program_num in budgets:
            return float(budgets[self._program_num].adjust)
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set the water budget percentage for this program."""
        adjust = int(value)
        try:
            await _set_water_budget(
                self.coordinator.controller, self._program_num, adjust
            )
        except RainbirdApiException as err:
            raise HomeAssistantError("Rain Bird device failure") from err

        # Update coordinator to reflect the new value.
        if self.coordinator.data.water_budgets is not None:
            budgets = dict(self.coordinator.data.water_budgets)
            budgets[self._program_num] = WaterBudget(self._program_num, adjust)
            self.coordinator.data.water_budgets = budgets
            self.async_write_ha_state()
        await self.coordinator.async_request_refresh()


class RainBirdZoneDurationNumber(
    CoordinatorEntity[RainbirdScheduleUpdateCoordinator], NumberEntity
):
    """Number entity for the run duration of a zone within a program."""

    _attr_native_min_value = 0
    _attr_native_max_value = 240
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:timer-outline"
    _attr_has_entity_name = True
    _attr_translation_key = "zone_duration"

    def __init__(
        self,
        schedule_coordinator: RainbirdScheduleUpdateCoordinator,
        update_coordinator: RainbirdUpdateCoordinator,
        zone_num: int,
        program_num: int,
        max_programs: int,
    ) -> None:
        """Initialize the zone duration number."""
        super().__init__(schedule_coordinator)
        self._zone_num = zone_num
        self._program_num = program_num
        self._max_programs = max_programs
        self._controller = update_coordinator.controller
        self._attr_unique_id = (
            f"{update_coordinator.unique_id}-zone-{zone_num}-duration-{program_num}"
        )
        self._attr_translation_placeholders = {"zone": str(zone_num)}
        self._attr_device_info = update_coordinator.program_device_info(program_num)

    @property
    def native_value(self) -> float | None:
        """Return the run duration in minutes for this zone and program."""
        schedule = self.coordinator.data
        if not schedule:
            return None
        for program in schedule.programs:
            if program.program == self._program_num:
                for zd in program.durations:
                    if zd.zone == self._zone_num:
                        return float(int(zd.duration.total_seconds() / 60))
                return 0.0
        return None

    async def async_added_to_hass(self) -> None:
        """Trigger a schedule refresh when added to hass."""
        await super().async_added_to_hass()
        self.coordinator.config_entry.async_create_background_task(
            self.hass,
            self.coordinator.async_request_refresh(),
            f"rainbird.zone-{self._zone_num}-program-{self._program_num}-refresh",
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set the run duration in minutes for this zone and program."""
        minutes = int(value)
        zone_page = (self._zone_num - 1) // 2

        # Build the full page from current schedule data, then patch the target slot.
        zone_durations: list[list[int]] = [
            [0] * self._max_programs,
            [0] * self._max_programs,
        ]
        schedule = self.coordinator.data
        if schedule:
            for program in schedule.programs:
                if program.program < self._max_programs:
                    for zd in program.durations:
                        page = (zd.zone - 1) // 2
                        if page == zone_page:
                            slot = (zd.zone - 1) % 2
                            zone_durations[slot][program.program] = int(
                                zd.duration.total_seconds() / 60
                            )

        slot = (self._zone_num - 1) % 2
        zone_durations[slot][self._program_num] = minutes

        try:
            await _set_zone_page_durations(self._controller, zone_page, zone_durations)
        except RainbirdApiException as err:
            raise HomeAssistantError("Rain Bird device failure") from err

        await self.coordinator.async_request_refresh()
