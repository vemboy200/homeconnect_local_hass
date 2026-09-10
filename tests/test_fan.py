"""Tests for fan entity."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock, patch

import pytest
from home_disconnect.entities import Program
from home_disconnect.message import Action, Message
from homeassistant.components.fan import (
    ATTR_PERCENTAGE,
    ATTR_PERCENTAGE_STEP,
    SERVICE_SET_PERCENTAGE,
    FanEntityFeature,
)
from homeassistant.components.fan import DOMAIN as FAN_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    ATTR_SUPPORTED_FEATURES,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from . import setup_config_entry
from .const import MOCK_CONFIG_DATA

if TYPE_CHECKING:
    from home_disconnect.testutils import MockAppliance
    from homeassistant.core import HomeAssistant


async def test_setup(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test setting up entity."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    state = hass.states.get("fan.fake_brand_homeappliance_fan")
    assert state
    assert state.name == "Fake_brand HomeAppliance Fan"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Fake_brand HomeAppliance Fan"
    assert (
        state.attributes[ATTR_SUPPORTED_FEATURES]
        == FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_OFF | FanEntityFeature.TURN_ON
        or
        state.attributes[ATTR_SUPPORTED_FEATURES]
        == FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE | FanEntityFeature.TURN_OFF | FanEntityFeature.TURN_ON
    )
    assert state.attributes[ATTR_PERCENTAGE_STEP] == 25


async def test_update(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test updating entity."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.ActiveProgram"].update({"value": 0})
    await hass.async_block_till_done()

    state = hass.states.get("fan.fake_brand_homeappliance_fan")
    assert state.state == STATE_OFF

    await mock_appliance.entities["Test.ActiveProgram"].update({"value": 504})
    await mock_appliance.entities["Test.FanSpeed1"].update({"value": 1})
    await hass.async_block_till_done()

    state = hass.states.get("fan.fake_brand_homeappliance_fan")
    assert state.state == STATE_ON
    assert state.attributes[ATTR_PERCENTAGE] == 25

    await mock_appliance.entities["Test.FanSpeed1"].update({"value": 2})
    await hass.async_block_till_done()

    state = hass.states.get("fan.fake_brand_homeappliance_fan")
    assert state.state == STATE_ON
    assert state.attributes[ATTR_PERCENTAGE] == 50

    await mock_appliance.entities["Test.FanSpeed1"].update({"value": 0})
    await mock_appliance.entities["Test.FanSpeed2"].update({"value": 1})
    await hass.async_block_till_done()

    state = hass.states.get("fan.fake_brand_homeappliance_fan")
    assert state.state == STATE_ON
    assert state.attributes[ATTR_PERCENTAGE] == 75

    await mock_appliance.entities["Test.FanSpeed1"].update({"value": 0})
    await mock_appliance.entities["Test.FanSpeed2"].update({"value": 2})
    await hass.async_block_till_done()

    state = hass.states.get("fan.fake_brand_homeappliance_fan")
    assert state.state == STATE_ON
    assert state.attributes[ATTR_PERCENTAGE] == 100


async def test_is_on_false_when_operation_state_inactive(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """
    Test the fan reports off when OperationState says so, despite a stale program.

    Some hoods keep reporting an active Venting program with a non-zero
    venting level after being switched off - confirmed live on fork issue
    #60. OperationState is the authoritative signal in that case.
    """
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.ActiveProgram"].update({"value": 504})
    await mock_appliance.entities["Test.FanSpeed1"].update({"value": 1})
    await hass.async_block_till_done()

    state = hass.states.get("fan.fake_brand_homeappliance_fan")
    assert state.state == STATE_ON

    mock_appliance.entities["BSH.Common.Status.OperationState"] = Mock(value="Inactive")
    # Not itself subscribed (it wasn't present at entity setup), but is_on
    # reads it fresh on every evaluation - re-triggering an already
    # subscribed entity's callback (the fan only subscribes to its speed
    # entities, not ActiveProgram) is enough to force a re-render.
    await mock_appliance.entities["Test.FanSpeed1"].update({"value": 1})
    await hass.async_block_till_done()

    state = hass.states.get("fan.fake_brand_homeappliance_fan")
    assert state.state == STATE_OFF


async def test_turn_on(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test turning on."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.ActiveProgram"].update({"value": 0})
    await hass.async_block_till_done()

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "fan.fake_brand_homeappliance_fan"},
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data={
                "program": 504,
                "options": [],
            },
        )
    )


async def test_turn_on_full_option_set(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """
    Test turning on sends a complete option set for appliances that need one.

    Same 400 BadRequest as the start button / program select: an appliance
    whose ActiveProgram is flagged fullOptionSet validates a program write
    against the program's complete option set and rejects an empty one.
    Confirmed live on a Bosch hood, fork issue #17.
    """
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.ActiveProgram"].update({"value": 0})
    await mock_appliance.entities["Test.Option1"].update({"value": True})
    await hass.async_block_till_done()

    with patch.object(Program, "full_option_set", new=True, create=True):
        await hass.services.async_call(
            FAN_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: "fan.fake_brand_homeappliance_fan"},
            blocking=True,
        )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data={
                "program": 504,
                "options": [
                    {"uid": 401, "value": True},
                    {"uid": 403, "value": 0},
                    {"uid": 404, "value": 0},
                ],
            },
        )
    )


async def test_turn_off(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """
    Test turning off writes PowerState to its off value.

    Neither writing 0 to the speed options nor DELETE /ro/activeProgram is
    honoured by every hood - confirmed live on a DWK81AN60 (fork issue #17,
    upstream #386/#387): DELETE is never answered at all, and the appliance
    only actually stops in response to a PowerState write.
    """
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.ActiveProgram"].update({"value": 504})
    await hass.async_block_till_done()

    power_state = Mock(enum={0: "Off", 1: "On"}, min=None, max=None, set_value=AsyncMock())
    mock_appliance.entities["BSH.Common.Setting.PowerState"] = power_state

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "fan.fake_brand_homeappliance_fan"},
        blocking=True,
    )

    power_state.set_value.assert_awaited_once_with("Off")
    mock_appliance.session.send_sync.assert_not_awaited()


async def test_turn_off_no_power_off_available(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test turning off raises when PowerState can't be set to Off/MainsOff."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.ActiveProgram"].update({"value": 504})
    await hass.async_block_till_done()

    power_state = Mock(enum={1: "On", 2: "Standby"}, min=None, max=None, set_value=AsyncMock())
    mock_appliance.entities["BSH.Common.Setting.PowerState"] = power_state

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            FAN_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: "fan.fake_brand_homeappliance_fan"},
            blocking=True,
        )

    power_state.set_value.assert_not_awaited()


async def test_turn_off_respects_settable_range(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test an Off enum member outside the entity's min/max range doesn't count."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.ActiveProgram"].update({"value": 504})
    await hass.async_block_till_done()

    # "Off" (0) is declared but outside the settable 1-2 range - matches
    # generate_power_switch's own handling of this same entity.
    power_state = Mock(enum={0: "Off", 1: "On", 2: "Standby"}, min=1, max=2, set_value=AsyncMock())
    mock_appliance.entities["BSH.Common.Setting.PowerState"] = power_state

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            FAN_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: "fan.fake_brand_homeappliance_fan"},
            blocking=True,
        )

    power_state.set_value.assert_not_awaited()


async def test_turn_off_command_timeout(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test a PowerState write that never gets answered raises a clear error."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.ActiveProgram"].update({"value": 504})
    await hass.async_block_till_done()

    power_state = Mock(
        enum={0: "Off", 1: "On"},
        min=None,
        max=None,
        set_value=AsyncMock(side_effect=TimeoutError),
    )
    mock_appliance.entities["BSH.Common.Setting.PowerState"] = power_state

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            FAN_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: "fan.fake_brand_homeappliance_fan"},
            blocking=True,
        )


async def test_turn_off_when_already_off(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test turning off when no program is active."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.ActiveProgram"].update({"value": 0})
    await hass.async_block_till_done()

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "fan.fake_brand_homeappliance_fan"},
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_not_awaited()


async def test_off_when_program_cleared_but_venting_stale(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Fan reports off when program ends even if venting level is stale."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.ActiveProgram"].update({"value": 504})
    await mock_appliance.entities["Test.FanSpeed1"].update({"value": 0})
    await mock_appliance.entities["Test.FanSpeed2"].update({"value": 2})
    await hass.async_block_till_done()

    state = hass.states.get("fan.fake_brand_homeappliance_fan")
    assert state.state == STATE_ON
    assert state.attributes[ATTR_PERCENTAGE] == 100

    await mock_appliance.entities["Test.ActiveProgram"].update({"value": 0})
    await mock_appliance.entities["Test.FanSpeed1"].update({"value": 0})
    await hass.async_block_till_done()

    state = hass.states.get("fan.fake_brand_homeappliance_fan")
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_PERCENTAGE] == 0


async def test_set_speed(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test setting a speed."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.ActiveProgram"].update({"value": 0})
    await mock_appliance.entities["Test.Option1"].update({"value": True})
    await hass.async_block_till_done()

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PERCENTAGE,
        {
            ATTR_ENTITY_ID: "fan.fake_brand_homeappliance_fan",
            ATTR_PERCENTAGE: 25,
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data={
                "program": 504,
                "options": [
                    {"uid": 403, "value": 1},
                    {"uid": 404, "value": 0},
                    {"uid": 401, "value": True},
                ],
            },
        )
    )
    mock_appliance.session.send_sync.reset_mock()

    await mock_appliance.entities["Test.ActiveProgram"].update({"value": 505})
    await hass.async_block_till_done()

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PERCENTAGE,
        {
            ATTR_ENTITY_ID: "fan.fake_brand_homeappliance_fan",
            ATTR_PERCENTAGE: 75,
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data={
                "program": 505,
                "options": [
                    {"uid": 403, "value": 0},
                    {"uid": 404, "value": 1},
                    {"uid": 401, "value": True},
                ],
            },
        )
    )
