"""Support for Rain Bird Irrigation system LNK Wi-Fi Module."""

import logging

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import RainbirdUpdateCoordinator
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
    coordinator = config_entry.runtime_data.coordinator

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
