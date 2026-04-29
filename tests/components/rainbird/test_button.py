"""Tests for rainbird button platform."""

from http import HTTPStatus

import pytest

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from homeassistant.components.rainbird import DOMAIN

from .conftest import (
    ACK_ECHO,
    mock_response,
    mock_response_error,
)

from tests.common import MockConfigEntry
from tests.test_util.aiohttp import AiohttpClientMocker, AiohttpClientMockResponse


@pytest.fixture
def platforms() -> list[str]:
    """Fixture to specify platforms to test."""
    return [Platform.BUTTON]


@pytest.fixture(autouse=True)
async def setup_config_entry(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Fixture to setup the config entry."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.LOADED


async def test_run_program_buttons(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test that run program buttons are created for each program."""
    button_a = hass.states.get("button.rain_bird_program_a_run")
    assert button_a is not None
    assert button_a.attributes.get("friendly_name") == "Rain Bird Program A Run"

    entity_entry = entity_registry.async_get("button.rain_bird_program_a_run")
    assert entity_entry
    assert entity_entry.unique_id == "4c:a1:61:00:11:22-run-program-0"

    button_b = hass.states.get("button.rain_bird_program_b_run")
    assert button_b is not None
    assert button_b.attributes.get("friendly_name") == "Rain Bird Program B Run"

    entity_entry = entity_registry.async_get("button.rain_bird_program_b_run")
    assert entity_entry
    assert entity_entry.unique_id == "4c:a1:61:00:11:22-run-program-1"

    button_c = hass.states.get("button.rain_bird_program_c_run")
    assert button_c is not None

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, "4c:a1:61:00:11:22-program-0")}
    )
    assert device
    assert device.name == "Rain Bird Program A"


async def test_press_run_button(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    responses: list[AiohttpClientMockResponse],
) -> None:
    """Test pressing a run program button sends the correct command."""
    aioclient_mock.mock_calls.clear()
    responses.append(mock_response(ACK_ECHO))

    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.rain_bird_program_a_run"},
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
async def test_press_run_button_error(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    responses: list[AiohttpClientMockResponse],
    status: HTTPStatus,
    expected_msg: str,
) -> None:
    """Test error handling when pressing a run program button."""
    aioclient_mock.mock_calls.clear()
    responses.append(mock_response_error(status=status))

    with pytest.raises(HomeAssistantError, match=expected_msg):
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {ATTR_ENTITY_ID: "button.rain_bird_program_a_run"},
            blocking=True,
        )

    assert len(aioclient_mock.mock_calls) == 1
