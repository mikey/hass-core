"""Tests for rainbird time platform."""

import datetime
from http import HTTPStatus

import pytest

from homeassistant.components.time import DOMAIN as TIME_DOMAIN, SERVICE_SET_VALUE
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_TIME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .conftest import (
    ACK_ECHO,
    mock_response,
    mock_response_error,
)

from tests.common import MockConfigEntry
from tests.test_util.aiohttp import AiohttpClientMocker, AiohttpClientMockResponse

# Schedule responses for ESP-TM2 (3 programs, 12 zones → 6 zone pages).
# Program 0 start time: 0x00F0 = 240 minutes = 04:00 AM.
# Programs 1 and 2 have no start time (0xFFFF).
SCHEDULE_RESPONSES = [
    "A0000000000000",
    "A00010060602006400",
    "A00011110602006400",
    "A00012000300006400",
    "A0006000F0FFFFFFFFFFFF",
    "A00061FFFFFFFFFFFFFFFF",
    "A00062FFFFFFFFFFFFFFFF",
    "A00080001900000000001400000000",
    "A00081000700000000001400000000",
    "A00082000A00000000000000000000",
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
    return [Platform.TIME]


@pytest.fixture(autouse=True)
async def setup_config_entry(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Fixture to setup the config entry."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.LOADED


@pytest.fixture(name="insert_schedule_responses")
def mock_insert_schedule_responses(
    responses: list[AiohttpClientMockResponse],
) -> None:
    """Append schedule responses for the start time entity refresh."""
    responses.extend(mock_response(r) for r in SCHEDULE_RESPONSES)


async def test_start_time_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    insert_schedule_responses: None,
) -> None:
    """Test that start time entities are created and show schedule data."""
    await hass.async_block_till_done()

    start_a = hass.states.get("time.rain_bird_program_a_start_time")
    assert start_a is not None
    assert start_a.state == "04:00:00"
    assert start_a.attributes.get("friendly_name") == "Rain Bird Program A Start time"

    entity_entry = entity_registry.async_get("time.rain_bird_program_a_start_time")
    assert entity_entry
    assert entity_entry.unique_id == "4c:a1:61:00:11:22-program-0-start-time"

    start_b = hass.states.get("time.rain_bird_program_b_start_time")
    assert start_b is not None
    assert start_b.state == "unknown"

    start_c = hass.states.get("time.rain_bird_program_c_start_time")
    assert start_c is not None


async def test_start_time_entity_no_schedule_data(
    hass: HomeAssistant,
) -> None:
    """Test that start time entity shows unknown when no schedule data is available."""
    start_a = hass.states.get("time.rain_bird_program_a_start_time")
    assert start_a is not None
    assert start_a.state == "unknown"


async def test_set_start_time(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    responses: list[AiohttpClientMockResponse],
    insert_schedule_responses: None,
) -> None:
    """Test setting a program start time issues the correct SIP command."""
    await hass.async_block_till_done()

    aioclient_mock.mock_calls.clear()
    responses.append(mock_response(ACK_ECHO))

    await hass.services.async_call(
        TIME_DOMAIN,
        SERVICE_SET_VALUE,
        {
            "entity_id": "time.rain_bird_program_a_start_time",
            ATTR_TIME: datetime.time(6, 0),
        },
        blocking=True,
    )

    assert len(aioclient_mock.mock_calls) == 1


async def test_set_start_time_error(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    responses: list[AiohttpClientMockResponse],
    insert_schedule_responses: None,
) -> None:
    """Test error handling when setting start time fails."""
    await hass.async_block_till_done()

    aioclient_mock.mock_calls.clear()
    responses.append(mock_response_error(HTTPStatus.INTERNAL_SERVER_ERROR))

    with pytest.raises(HomeAssistantError, match="Rain Bird device failure"):
        await hass.services.async_call(
            TIME_DOMAIN,
            SERVICE_SET_VALUE,
            {
                "entity_id": "time.rain_bird_program_a_start_time",
                ATTR_TIME: datetime.time(6, 0),
            },
            blocking=True,
        )
