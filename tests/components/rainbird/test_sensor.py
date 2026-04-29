"""Tests for rainbird sensor platform."""

from http import HTTPStatus

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import (
    AVAILABLE_STATIONS_RESPONSE,
    COMBINED_CONTROLLER_STATE_RESPONSE,
    COMBINED_CONTROLLER_STATE_UNSUPPORTED,
    CONFIG_ENTRY_DATA_OLD_FORMAT,
    MODEL_AND_VERSION_RESPONSE,
    RAIN_DELAY,
    RAIN_DELAY_OFF,
    RAIN_SENSOR_OFF,
    ZONE_STATE_OFF_RESPONSE,
    mock_response_error,
)

from tests.common import MockConfigEntry
from tests.test_util.aiohttp import AiohttpClientMockResponse

_BASE_API_RESPONSES = [
    MODEL_AND_VERSION_RESPONSE,
    AVAILABLE_STATIONS_RESPONSE,
    ZONE_STATE_OFF_RESPONSE,
    RAIN_SENSOR_OFF,
    RAIN_DELAY_OFF,
]


@pytest.fixture
def platforms() -> list[str]:
    """Fixture to specify platforms to test."""
    return [Platform.SENSOR]


@pytest.fixture(autouse=True)
async def setup_config_entry(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> list[Platform]:
    """Fixture to setup the config entry."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.LOADED


@pytest.mark.parametrize(
    ("rain_delay_response", "expected_state"),
    [(RAIN_DELAY, "16"), (RAIN_DELAY_OFF, "0")],
)
async def test_sensors(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    expected_state: str,
) -> None:
    """Test sensor platform."""

    raindelay = hass.states.get("sensor.rain_bird_controller_rain_delay")
    assert raindelay is not None
    assert raindelay.state == expected_state
    assert raindelay.attributes == {
        "friendly_name": "Rain Bird Controller Rain delay",
    }

    entity_entry = entity_registry.async_get("sensor.rain_bird_controller_rain_delay")
    assert entity_entry
    assert entity_entry.unique_id == "4c:a1:61:00:11:22-raindelay"


@pytest.mark.parametrize(
    "api_responses",
    [[*_BASE_API_RESPONSES, COMBINED_CONTROLLER_STATE_RESPONSE]],
)
async def test_controller_state_sensors(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that controller state sensors show correct values."""
    remaining = hass.states.get("sensor.rain_bird_controller_remaining_runtime")
    assert remaining is not None
    assert remaining.state == "120"

    entity_entry = entity_registry.async_get(
        "sensor.rain_bird_controller_remaining_runtime"
    )
    assert entity_entry
    assert entity_entry.unique_id == "4c:a1:61:00:11:22-remaining-runtime"

    active = hass.states.get("sensor.rain_bird_controller_active_station")
    assert active is not None
    assert active.state == "3"

    entity_entry = entity_registry.async_get(
        "sensor.rain_bird_controller_active_station"
    )
    assert entity_entry
    assert entity_entry.unique_id == "4c:a1:61:00:11:22-active-station"

    seasonal = hass.states.get("sensor.rain_bird_controller_seasonal_adjustment")
    assert seasonal is not None
    assert seasonal.state == "100"

    entity_entry = entity_registry.async_get(
        "sensor.rain_bird_controller_seasonal_adjustment"
    )
    assert entity_entry
    assert entity_entry.unique_id == "4c:a1:61:00:11:22-seasonal-adjust"


@pytest.mark.parametrize(
    "api_responses",
    [[*_BASE_API_RESPONSES, COMBINED_CONTROLLER_STATE_UNSUPPORTED]],
)
async def test_seasonal_adjust_not_created_when_unsupported(
    hass: HomeAssistant,
) -> None:
    """Test that seasonal adjustment sensor is not created when the device reports 0xFFFF."""
    assert hass.states.get("sensor.rain_bird_controller_seasonal_adjustment") is None


async def test_controller_state_sensors_unavailable_without_data(
    hass: HomeAssistant,
) -> None:
    """Test controller state sensors return unknown when no controller state data available."""
    remaining = hass.states.get("sensor.rain_bird_controller_remaining_runtime")
    assert remaining is not None
    assert remaining.state == "unknown"

    active = hass.states.get("sensor.rain_bird_controller_active_station")
    assert active is not None
    assert active.state == "unknown"


@pytest.mark.parametrize(
    ("config_entry_unique_id", "config_entry_data", "setup_config_entry"),
    [
        # Config entry setup without a unique id since it had no serial number
        (
            None,
            {
                **CONFIG_ENTRY_DATA_OLD_FORMAT,
                "serial_number": 0,
            },
            None,
        ),
    ],
)
async def test_sensor_no_unique_id(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    responses: list[AiohttpClientMockResponse],
    config_entry_unique_id: str | None,
    config_entry: MockConfigEntry,
) -> None:
    """Test sensor platform with no unique id."""

    # Failure to migrate config entry to a unique id
    responses.insert(1, mock_response_error(HTTPStatus.SERVICE_UNAVAILABLE))

    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.LOADED

    raindelay = hass.states.get("sensor.rain_bird_controller_rain_delay")
    assert raindelay is not None
    assert (
        raindelay.attributes.get("friendly_name") == "Rain Bird Controller Rain delay"
    )

    entity_entry = entity_registry.async_get("sensor.rain_bird_controller_rain_delay")
    assert (entity_entry is None) == (config_entry_unique_id is None)
