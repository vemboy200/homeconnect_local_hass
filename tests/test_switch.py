"""Tests for switch entity."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from custom_components.homeconnect_ws import HCData
from custom_components.homeconnect_ws.entity_descriptions.descriptions_definitions import (
    HCSwitchEntityDescription,
)
from custom_components.homeconnect_ws.switch import HCSwitch
from home_disconnect.message import Action, Message
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
)

from . import setup_config_entry
from .const import MOCK_CONFIG_DATA

if TYPE_CHECKING:
    from home_disconnect.testutils import MockAppliance
    from homeassistant.core import HomeAssistant


async def test_setup(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,  # noqa: ARG001
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """Test setting up entity."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    state = hass.states.get("switch.fake_brand_homeappliance_switch")
    assert state
    assert state.state == STATE_OFF
    assert state.name == "Fake_brand HomeAppliance Switch"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Fake_brand HomeAppliance Switch"

    state = hass.states.get("switch.fake_brand_homeappliance_switch_enum")
    assert state
    assert state.state == STATE_UNKNOWN
    assert state.name == "Fake_brand HomeAppliance Switch.Enum"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Fake_brand HomeAppliance Switch.Enum"


async def test_update(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """Test updating entity."""
    entity_id = "switch.fake_brand_homeappliance_switch"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await mock_appliance.entities["Test.Switch"].update({"value": False})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state
    assert state.state == STATE_OFF

    await mock_appliance.entities["Test.Switch"].update({"value": True})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state
    assert state.state == STATE_ON


async def test_update_enum(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """Test updating entity with enum."""
    entity_id = "switch.fake_brand_homeappliance_switch_enum"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await mock_appliance.entities["Test.Switch.Enum"].update({"value": 0})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state
    assert state.state == STATE_OFF

    await mock_appliance.entities["Test.Switch.Enum"].update({"value": 1})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state
    assert state.state == STATE_ON


async def test_turn_on(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """Test turning on."""
    entity_id = "switch.fake_brand_homeappliance_switch"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await hass.services.async_call(
        domain=SWITCH_DOMAIN,
        service=SERVICE_TURN_ON,
        service_data={ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data={"uid": 201, "value": True},
        )
    )


async def test_turn_on_enum(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """Test turning on with enum."""
    entity_id = "switch.fake_brand_homeappliance_switch_enum"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await hass.services.async_call(
        domain=SWITCH_DOMAIN,
        service=SERVICE_TURN_ON,
        service_data={ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )
    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data={"uid": 202, "value": 1},
        )
    )


async def test_turn_off(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """Test turning off."""
    entity_id = "switch.fake_brand_homeappliance_switch"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await hass.services.async_call(
        domain=SWITCH_DOMAIN,
        service=SERVICE_TURN_OFF,
        service_data={ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data={"uid": 201, "value": False},
        )
    )


async def test_turn_off_enum(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """Test turning off with enum."""
    entity_id = "switch.fake_brand_homeappliance_switch_enum"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await hass.services.async_call(
        domain=SWITCH_DOMAIN,
        service=SERVICE_TURN_OFF,
        service_data={ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )
    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data={"uid": 202, "value": 0},
        )
    )


async def test_is_on_forced_off_when_expected_offline() -> None:
    """A laundry appliance's power_state switch shows off, not its stale value."""
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=True),
    )
    entity_description = HCSwitchEntityDescription(
        key="switch_power_state",
        value_mapping=("On", "Off"),
        force_off_when_expected_offline=True,
    )
    entity = HCSwitch(entity_description, runtime_data)

    assert entity.is_on is False


async def test_is_on_not_forced_when_not_expected_offline() -> None:
    """The forced-off value only applies while actually expected_offline."""
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=False),
    )
    entity_description = HCSwitchEntityDescription(
        key="switch_power_state",
        value_mapping=("On", "Off"),
        force_off_when_expected_offline=True,
    )
    entity = HCSwitch(entity_description, runtime_data)

    assert entity.is_on is None
