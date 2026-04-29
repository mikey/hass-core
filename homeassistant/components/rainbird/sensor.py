"""Support for Rain Bird Irrigation system LNK Wi-Fi Module."""

from __future__ import annotations

import datetime
import logging
from typing import Any

from pyrainbird.data import Program, Schedule

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import RainbirdScheduleUpdateCoordinator, RainbirdUpdateCoordinator
from .types import RainbirdConfigEntry

_LOGGER = logging.getLogger(__name__)


RAIN_DELAY_ENTITY_DESCRIPTION = SensorEntityDescription(
    key="raindelay",
    translation_key="raindelay",
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: RainbirdConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up entry for a Rain Bird sensor."""
    data = config_entry.runtime_data
    coordinator = data.coordinator

    entities: list[SensorEntity] = [
        RainBirdSensor(coordinator, RAIN_DELAY_ENTITY_DESCRIPTION),
    ]

    # Controller state sensors (remaining runtime, active station, seasonal adjust).
    if coordinator.unique_id is not None:
        entities.extend(
            [
                RainBirdRemainingRuntimeSensor(coordinator),
                RainBirdActiveStationSensor(coordinator),
            ]
        )
        # Seasonal adjustment is only supported on some models (0xFFFF = unsupported).
        state = coordinator.data.controller_state
        if state is not None and state.seasonal_adjust != 0xFFFF:
            entities.append(RainBirdSeasonalAdjustSensor(coordinator))

    # Program total runtime sensor — one per program device.
    max_programs = data.model_info.model_info.max_programs
    if max_programs:
        entities.extend(
            RainBirdProgramSensor(
                data.schedule_coordinator,
                coordinator,
                program_num,
            )
            for program_num in range(max_programs)
        )

    async_add_entities(entities)


class RainBirdSensor(CoordinatorEntity[RainbirdUpdateCoordinator], SensorEntity):
    """A sensor implementation for Rain Bird device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RainbirdUpdateCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the Rain Bird sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        if coordinator.unique_id is not None:
            self._attr_unique_id = f"{coordinator.unique_id}-{description.key}"
            self._attr_device_info = coordinator.device_info
            self._attr_name = "Rain delay"
        else:
            self._attr_name = f"{coordinator.device_name} Rain delay"

    @property
    def native_value(self) -> StateType:
        """Return the value reported by the sensor."""
        return self.coordinator.data.rain_delay


class RainBirdSeasonalAdjustSensor(
    CoordinatorEntity[RainbirdUpdateCoordinator], SensorEntity
):
    """Sensor for the controller's global seasonal adjustment percentage."""

    _attr_has_entity_name = True
    _attr_translation_key = "seasonal_adjust"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:water-percent"

    def __init__(self, coordinator: RainbirdUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_id}-seasonal-adjust"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> StateType:
        """Return the seasonal adjustment percentage."""
        if (state := self.coordinator.data.controller_state) is not None:
            # 0xFFFF means not supported by this controller model.
            if state.seasonal_adjust == 0xFFFF:
                return None
            return state.seasonal_adjust
        return None


class RainBirdRemainingRuntimeSensor(
    CoordinatorEntity[RainbirdUpdateCoordinator], SensorEntity
):
    """Sensor for the remaining irrigation runtime."""

    _attr_has_entity_name = True
    _attr_translation_key = "remaining_runtime"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator: RainbirdUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_id}-remaining-runtime"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> StateType:
        """Return remaining runtime in seconds."""
        if (state := self.coordinator.data.controller_state) is not None:
            return state.remaining_runtime
        return None


class RainBirdActiveStationSensor(
    CoordinatorEntity[RainbirdUpdateCoordinator], SensorEntity
):
    """Sensor for the currently active station/zone."""

    _attr_has_entity_name = True
    _attr_translation_key = "active_station"
    _attr_icon = "mdi:sprinkler-variant"

    def __init__(self, coordinator: RainbirdUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_id}-active-station"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> StateType:
        """Return the active station number, or 0 if none."""
        if (state := self.coordinator.data.controller_state) is not None:
            return state.active_station
        return None


def _format_time(t: datetime.time) -> str:
    """Format a time as HH:MM."""
    return t.strftime("%H:%M")


def _format_timedelta(td: datetime.timedelta) -> int:
    """Format a timedelta as total minutes."""
    return int(td.total_seconds() / 60)


def _get_program(schedule: Schedule | None, program_num: int) -> Program | None:
    """Get a program from the schedule by number."""
    if not schedule or not schedule.programs:
        return None
    for program in schedule.programs:
        if program.program == program_num:
            return program
    return None


class RainBirdProgramSensor(
    CoordinatorEntity[RainbirdScheduleUpdateCoordinator], SensorEntity
):
    """Sensor showing the total runtime for a program."""

    _attr_has_entity_name = True
    _attr_translation_key = "program"
    _attr_icon = "mdi:clock-outline"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(
        self,
        schedule_coordinator: RainbirdScheduleUpdateCoordinator,
        update_coordinator: RainbirdUpdateCoordinator,
        program_num: int,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(schedule_coordinator)
        self._program_num = program_num
        self._attr_unique_id = (
            f"{update_coordinator.unique_id}-program-{program_num}"
        )
        self._attr_device_info = update_coordinator.program_device_info(program_num)

    @property
    def native_value(self) -> StateType:
        """Return total program duration in minutes."""
        program = _get_program(self.coordinator.data, self._program_num)
        if not program:
            return None
        total_minutes = _format_timedelta(program.duration)
        return total_minutes if total_minutes > 0 else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return program schedule details as attributes."""
        program = _get_program(self.coordinator.data, self._program_num)
        if not program:
            return {}

        attrs: dict[str, Any] = {}
        attrs["frequency"] = program.frequency.name.lower()

        if program.days_of_week:
            attrs["days_of_week"] = sorted(
                [day.name.lower() for day in program.days_of_week]
            )

        if program.period is not None:
            attrs["period_days"] = program.period

        return attrs

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self.coordinator.config_entry.async_create_background_task(
            self.hass,
            self.coordinator.async_request_refresh(),
            f"rainbird.program-{self._program_num}-refresh",
        )


