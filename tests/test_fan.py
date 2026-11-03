"""Tests for fan entity."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from home_disconnect.messages import Action, Message
from homeassistant.components.fan import (
    ATTR_PERCENTAGE,
    ATTR_PRESET_MODE,
    SERVICE_SET_PERCENTAGE,
    SERVICE_SET_PRESET_MODE,
)
from homeassistant.components.fan import DOMAIN as FAN_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    Platform,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import snapshot_platform

from . import setup_integration, update_entity

if TYPE_CHECKING:
    from home_disconnect import Appliance
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from syrupy.assertion import SnapshotAssertion

ENTITY_ID = "fan.fake_brand_hood_fan"


async def _notify(appliance: Appliance, values: dict[int, Any]) -> None:
    """Apply values by UID, the way the hood reports them."""
    for uid, value in values.items():
        await update_entity(appliance.entities.by_uid[uid], {"value": value})


def _venting(options: list[tuple[int, Any]]) -> Message:
    """Return the write that starts the Venting program with these options."""
    return Message(
        resource="/ro/activeProgram",
        action=Action.POST,
        data=[
            {
                "program": 55307,
                "options": [{"uid": uid, "value": value} for uid, value in options],
            }
        ],
    )


@pytest.mark.usefixtures("mock_hood")
async def test_fan(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    hood_config_entry: MockConfigEntry,
) -> None:
    """Test the fan entity of a hood venting at the lowest level."""
    with patch("custom_components.homeconnect_ws.PLATFORMS", [Platform.FAN]):
        await setup_integration(hass, hood_config_entry)

    await snapshot_platform(hass, entity_registry, snapshot, hood_config_entry.entry_id)


@pytest.mark.parametrize(
    ("values", "expected_state", "expected_percentage"),
    [
        ({55308: 3}, STATE_ON, 60),
        ({55308: 0, 55305: 1}, STATE_ON, 80),
        ({55308: 0, 55305: 2}, STATE_ON, 100),
        # Boost runs Venting with both levels at 0 (fork issue #260)
        ({55308: 0, 55305: 0, 55297: True}, STATE_ON, 100),
        # Some hoods keep the program and level after switching off (fork issue #60)
        ({552: 0}, STATE_OFF, 0),
        ({256: 0}, STATE_OFF, 0),
    ],
)
async def test_state(
    hass: HomeAssistant,
    mock_hood: Appliance,
    hood_config_entry: MockConfigEntry,
    values: dict[int, Any],
    expected_state: str,
    expected_percentage: int,
) -> None:
    """Test the fan follows the hood's program, levels and operation state."""
    await setup_integration(hass, hood_config_entry)

    await _notify(mock_hood, values)
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state == expected_state
    assert state.attributes[ATTR_PERCENTAGE] == expected_percentage


async def test_boost_ends(
    hass: HomeAssistant,
    mock_hood: Appliance,
    hood_config_entry: MockConfigEntry,
) -> None:
    """Test the fan goes back to the hood's level when boost ends."""
    await setup_integration(hass, hood_config_entry)
    await _notify(mock_hood, {55308: 0, 55297: True})
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).attributes[ATTR_PRESET_MODE] == "Boost"

    await _notify(mock_hood, {55308: 1, 55297: False})
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_PERCENTAGE] == 20
    assert state.attributes[ATTR_PRESET_MODE] == "None"


async def test_turn_on(
    hass: HomeAssistant,
    mock_hood: Appliance,
    hood_config_entry: MockConfigEntry,
) -> None:
    """Test turning on starts Venting with every option, as this hood wants."""
    await setup_integration(hass, hood_config_entry)
    # What the hood reports when switched off; the levels keep their last value
    await _notify(mock_hood, {539: 1, 552: 0, 256: 0})
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_OFF

    await hass.services.async_call(
        FAN_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )

    mock_hood.session.request.assert_awaited_once_with(
        _venting([(55308, 1), (55305, 0), (55297, False)])
    )


@pytest.mark.parametrize(
    ("percentage", "options"),
    [
        (40, [(55308, 2), (55305, 0), (55297, False)]),
        (80, [(55308, 0), (55305, 1), (55297, False)]),
    ],
)
async def test_set_percentage(
    hass: HomeAssistant,
    mock_hood: Appliance,
    hood_config_entry: MockConfigEntry,
    percentage: int,
    options: list[tuple[int, Any]],
) -> None:
    """Test setting a speed writes the matching venting or intensive level."""
    await setup_integration(hass, hood_config_entry)

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PERCENTAGE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_PERCENTAGE: percentage},
        blocking=True,
    )

    mock_hood.session.request.assert_awaited_once_with(_venting(options))


async def test_set_percentage_ignores_remote_start(
    hass: HomeAssistant,
    mock_hood: Appliance,
    hood_config_entry: MockConfigEntry,
) -> None:
    """Test the fan still runs when the hood reports remote start as off."""
    await setup_integration(hass, hood_config_entry)
    await _notify(mock_hood, {517: False})
    await hass.async_block_till_done()

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PERCENTAGE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_PERCENTAGE: 40},
        blocking=True,
    )

    mock_hood.session.request.assert_awaited_once_with(
        _venting([(55308, 2), (55305, 0), (55297, False)])
    )


@pytest.mark.parametrize(
    ("preset_mode", "options"),
    [
        ("Boost", [(55308, 0), (55297, True), (55305, 0)]),
        ("None", []),
    ],
)
async def test_set_preset_mode(
    hass: HomeAssistant,
    mock_hood: Appliance,
    hood_config_entry: MockConfigEntry,
    preset_mode: str,
    options: list[tuple[int, Any]],
) -> None:
    """Test starting and stopping boost, shown right away before the hood confirms it."""
    await setup_integration(hass, hood_config_entry)

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_PRESET_MODE: preset_mode},
        blocking=True,
    )

    mock_hood.session.request.assert_awaited_once_with(_venting(options))
    assert hass.states.get(ENTITY_ID).attributes[ATTR_PRESET_MODE] == preset_mode


async def test_turn_off(
    hass: HomeAssistant,
    mock_hood: Appliance,
    hood_config_entry: MockConfigEntry,
) -> None:
    """
    Test turning off powers the hood off.

    Neither writing 0 to the levels nor DELETE /ro/activeProgram is honoured by every hood -
    confirmed live on a DWK81AN60 (fork issue #17, upstream #386/#387): DELETE is never
    answered at all, and the hood only stops on a PowerState write.
    """
    await setup_integration(hass, hood_config_entry)

    await hass.services.async_call(
        FAN_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )

    mock_hood.session.request.assert_awaited_once_with(
        Message(resource="/ro/values", action=Action.POST, data=[{"uid": 539, "value": 1}])
    )


@pytest.mark.parametrize(
    "hood_power_state",
    [
        {"enumeration": {"2": "On", "3": "Standby"}},
        # Off is declared but outside the settable range
        {"min": 2, "max": 3},
    ],
)
async def test_turn_off_no_power_off(
    hass: HomeAssistant,
    mock_hood: Appliance,
    hood_config_entry: MockConfigEntry,
) -> None:
    """Test turning off raises when PowerState can't be set to Off or MainsOff."""
    await setup_integration(hass, hood_config_entry)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            FAN_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
        )

    mock_hood.session.request.assert_not_awaited()


async def test_turn_off_timeout(
    hass: HomeAssistant,
    mock_hood: Appliance,
    hood_config_entry: MockConfigEntry,
) -> None:
    """Test a PowerState write that never gets answered raises a clear error."""
    await setup_integration(hass, hood_config_entry)
    mock_hood.session.request.side_effect = TimeoutError

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            FAN_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
        )


async def test_turn_off_when_already_off(
    hass: HomeAssistant,
    mock_hood: Appliance,
    hood_config_entry: MockConfigEntry,
) -> None:
    """Test turning off sends nothing when no program is running."""
    await setup_integration(hass, hood_config_entry)
    await _notify(mock_hood, {256: 0})
    await hass.async_block_till_done()

    await hass.services.async_call(
        FAN_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )

    mock_hood.session.request.assert_not_awaited()
