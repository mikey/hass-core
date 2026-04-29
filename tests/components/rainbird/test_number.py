"""Tests for rainbird number platform."""

from http import HTTPStatus

import pytest

from homeassistant.components import number
from homeassistant.components.rainbird import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import (
    ACK_ECHO,
    AVAILABLE_STATIONS_RESPONSE,
    COMBINED_CONTROLLER_STATE_RESPONSE,
    CONFIG_ENTRY_DATA_OLD_FORMAT,
    MAC_ADDRESS,
    MODEL_AND_VERSION_RESPONSE,
    RAIN_DELAY,
    RAIN_DELAY_OFF,
    RAIN_SENSOR_OFF,
    WATER_BUDGET_RESPONSE,
    ZONE_STATE_OFF_RESPONSE,
    mock_response,
    mock_response_error,
)

from tests.common import MockConfigEntry
from tests.test_util.aiohttp import AiohttpClientMocker, AiohttpClientMockResponse

_BASE_API_RESPONSES = [
    MODEL_AND_VERSION_RESPONSE,
    AVAILABLE_STATIONS_RESPONSE,
    ZONE_STATE_OFF_RESPONSE,
    RAIN_SENSOR_OFF,
    RAIN_DELAY_OFF,
]

# api_responses for tests needing water budget data.
# Coordinator calls: model(cached), stations, zone_states, rain, delay, controller_state, budget×3
_WATER_BUDGET_API_RESPONSES = [
    *_BASE_API_RESPONSES,
    COMBINED_CONTROLLER_STATE_RESPONSE,
    WATER_BUDGET_RESPONSE,  # program 0
    WATER_BUDGET_RESPONSE,  # program 1
    WATER_BUDGET_RESPONSE,  # program 2
]

# Schedule responses from get_schedule() for zone duration tests.
SCHEDULE_RESPONSES = [
    "A0000000000000",
    "A00010060602006400",
    "A00011110602006400",
    "A00012000300006400",
    "A0006000F0FFFFFFFFFFFF",
    "A00061FFFFFFFFFFFFFFFF",
    "A00062FFFFFFFFFFFFFFFF",
    "A00080001900000000001400000000",  # zone1=25min, zone2=20min (pgm0)
    "A00081000700000000001400000000",  # zone3=7min, zone4=20min (pgm0)
    "A00082000A00000000000000000000",  # zone5=10min (pgm0)
    "A00083000000000000000000000000",
    "A00084000000000000000000000000",
    "A00085000000000000000000000000",
    "A00086000000000000000000000000",
    "A00087000000000000000000000000",
    "A00088000000000000000000000000",
    "A00089000000000000000000000000",
    "A0008A000000000000000000000000",
]


@pytest.fixture
def platforms() -> list[str]:
    """Fixture to specify platforms to test."""
    return [Platform.NUMBER]


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
async def test_number_values(
    hass: HomeAssistant,
    expected_state: str,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test number platform."""

    raindelay = hass.states.get("number.rain_bird_controller_rain_delay")
    assert raindelay is not None
    assert raindelay.state == expected_state
    assert raindelay.attributes == {
        "friendly_name": "Rain Bird Controller Rain delay",
        "min": 0,
        "max": 14,
        "mode": "auto",
        "step": 1,
        "unit_of_measurement": "d",
    }

    entity_entry = entity_registry.async_get("number.rain_bird_controller_rain_delay")
    assert entity_entry
    assert entity_entry.unique_id == "4c:a1:61:00:11:22-rain-delay"


async def test_set_value(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    aioclient_mock: AiohttpClientMocker,
    responses: list[str],
) -> None:
    """Test setting the rain delay number."""

    raindelay = hass.states.get("number.rain_bird_controller_rain_delay")
    assert raindelay is not None

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, MAC_ADDRESS.lower())}
    )
    assert device
    assert device.name == "Rain Bird Controller"
    assert device.model == "ESP-TM2"
    assert device.sw_version == "9.12"

    aioclient_mock.mock_calls.clear()
    responses.append(mock_response(ACK_ECHO))

    await hass.services.async_call(
        number.DOMAIN,
        number.SERVICE_SET_VALUE,
        {
            ATTR_ENTITY_ID: "number.rain_bird_controller_rain_delay",
            number.ATTR_VALUE: 3,
        },
        blocking=True,
    )

    assert len(aioclient_mock.mock_calls) == 1


@pytest.mark.parametrize(
    ("status", "expected_msg"),
    [
        (HTTPStatus.SERVICE_UNAVAILABLE, "Rain Bird device is busy"),
        (HTTPStatus.INTERNAL_SERVER_ERROR, "Rain Bird device failure"),
    ],
)
async def test_set_value_error(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    responses: list[str],
    status: HTTPStatus,
    expected_msg: str,
) -> None:
    """Test an error while talking to the device."""

    aioclient_mock.mock_calls.clear()
    responses.append(mock_response_error(status=status))

    with pytest.raises(HomeAssistantError, match=expected_msg):
        await hass.services.async_call(
            number.DOMAIN,
            number.SERVICE_SET_VALUE,
            {
                ATTR_ENTITY_ID: "number.rain_bird_controller_rain_delay",
                number.ATTR_VALUE: 3,
            },
            blocking=True,
        )

    assert len(aioclient_mock.mock_calls) == 1


@pytest.mark.parametrize(
    ("config_entry_data", "config_entry_unique_id", "setup_config_entry"),
    [
        (CONFIG_ENTRY_DATA_OLD_FORMAT, None, None),
    ],
)
async def test_no_unique_id(
    hass: HomeAssistant,
    responses: list[AiohttpClientMockResponse],
    entity_registry: er.EntityRegistry,
    config_entry: MockConfigEntry,
) -> None:
    """Test number platform with no unique id."""

    # Failure to migrate config entry to a unique id
    responses.insert(1, mock_response_error(HTTPStatus.SERVICE_UNAVAILABLE))

    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.LOADED

    raindelay = hass.states.get("number.rain_bird_controller_rain_delay")
    assert raindelay is not None
    assert (
        raindelay.attributes.get("friendly_name") == "Rain Bird Controller Rain delay"
    )

    entity_entry = entity_registry.async_get("number.rain_bird_controller_rain_delay")
    assert not entity_entry


@pytest.mark.parametrize(
    "api_responses",
    [_WATER_BUDGET_API_RESPONSES],
)
async def test_water_budget_number(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test that water budget number entities are created with correct values."""
    budget_a = hass.states.get("number.rain_bird_program_a_seasonal_adjustment")
    assert budget_a is not None
    assert budget_a.state == "100.0"
    assert budget_a.attributes.get("friendly_name") == "Rain Bird Program A Seasonal adjustment"

    entity_entry = entity_registry.async_get(
        "number.rain_bird_program_a_seasonal_adjustment"
    )
    assert entity_entry
    assert entity_entry.unique_id == "4c:a1:61:00:11:22-water-budget-number-0"

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, "4c:a1:61:00:11:22-program-0")}
    )
    assert device
    assert device.name == "Rain Bird Program A"


@pytest.mark.parametrize(
    "api_responses",
    [_WATER_BUDGET_API_RESPONSES],
)
async def test_set_water_budget(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    responses: list[AiohttpClientMockResponse],
) -> None:
    """Test setting the water budget (seasonal adjustment) for a program."""
    aioclient_mock.mock_calls.clear()
    responses.append(mock_response(ACK_ECHO))

    await hass.services.async_call(
        number.DOMAIN,
        number.SERVICE_SET_VALUE,
        {
            ATTR_ENTITY_ID: "number.rain_bird_program_a_seasonal_adjustment",
            number.ATTR_VALUE: 80,
        },
        blocking=True,
    )

    # Main coordinator refresh is debounced (immediate=False), so only the
    # tunnelSip WaterBudgetSet command is made immediately.
    assert len(aioclient_mock.mock_calls) == 1


@pytest.mark.parametrize(
    "api_responses",
    [_WATER_BUDGET_API_RESPONSES],
)
async def test_set_water_budget_error(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    responses: list[AiohttpClientMockResponse],
) -> None:
    """Test error handling when setting water budget fails."""
    aioclient_mock.mock_calls.clear()
    responses.append(mock_response_error(HTTPStatus.INTERNAL_SERVER_ERROR))

    with pytest.raises(HomeAssistantError, match="Rain Bird device failure"):
        await hass.services.async_call(
            number.DOMAIN,
            number.SERVICE_SET_VALUE,
            {
                ATTR_ENTITY_ID: "number.rain_bird_program_a_seasonal_adjustment",
                number.ATTR_VALUE: 80,
            },
            blocking=True,
        )


@pytest.fixture(name="insert_schedule_responses")
def mock_insert_schedule_responses(
    responses: list[AiohttpClientMockResponse],
) -> None:
    """Append schedule responses needed for zone duration entities."""
    responses.extend(mock_response(r) for r in SCHEDULE_RESPONSES)


@pytest.mark.parametrize(
    "api_responses",
    [_WATER_BUDGET_API_RESPONSES],
)
async def test_zone_duration_number(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    insert_schedule_responses: None,
) -> None:
    """Test zone duration number entities show schedule data after refresh."""
    await hass.async_block_till_done()

    zone1_a = hass.states.get("number.rain_bird_program_a_zone_1")
    assert zone1_a is not None
    assert zone1_a.state == "25.0"
    assert zone1_a.attributes.get("friendly_name") == "Rain Bird Program A Zone 1"

    entity_entry = entity_registry.async_get("number.rain_bird_program_a_zone_1")
    assert entity_entry
    assert entity_entry.unique_id == "4c:a1:61:00:11:22-zone-1-duration-0"


@pytest.mark.parametrize(
    "api_responses",
    [_WATER_BUDGET_API_RESPONSES],
)
async def test_set_zone_duration(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    responses: list[AiohttpClientMockResponse],
    insert_schedule_responses: None,
) -> None:
    """Test setting the zone duration for a zone within a program."""
    await hass.async_block_till_done()

    aioclient_mock.mock_calls.clear()
    responses.append(mock_response(ACK_ECHO))

    await hass.services.async_call(
        number.DOMAIN,
        number.SERVICE_SET_VALUE,
        {
            ATTR_ENTITY_ID: "number.rain_bird_program_a_zone_1",
            number.ATTR_VALUE: 30,
        },
        blocking=True,
    )

    # Schedule coordinator refresh is debounced after initial refresh,
    # so only the tunnelSip SetSchedule command is made immediately.
    assert len(aioclient_mock.mock_calls) == 1
