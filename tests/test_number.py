"""Tests for number entity."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from custom_components.homeconnect_ws import HCData
from custom_components.homeconnect_ws.entity_descriptions.descriptions_definitions import (
    HCNumberEntityDescription,
)
from custom_components.homeconnect_ws.number import HCNumber
from home_disconnect.messages import Action, Message
from homeassistant.components.number import (
    ATTR_MAX,
    ATTR_MIN,
    ATTR_STEP,
    ATTR_VALUE,
    SERVICE_SET_VALUE,
)
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, ATTR_FRIENDLY_NAME

from . import setup_config_entry, update_entity
from .const import MOCK_CONFIG_DATA

if TYPE_CHECKING:
    from home_disconnect import Appliance
    from homeassistant.core import HomeAssistant


async def test_setup(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_entity_description: None,
) -> None:
    """Test setting up entity."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    state = hass.states.get("number.fake_brand_homeappliance_number")
    assert state
    assert state.name == "Fake_brand HomeAppliance Number"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Fake_brand HomeAppliance Number"
    assert state.attributes[ATTR_MIN] == 0
    assert state.attributes[ATTR_MAX] == 20
    assert state.attributes[ATTR_STEP] == 2


async def test_update(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_entity_description: None,
) -> None:
    """Test updating entity."""
    entity_id = "number.fake_brand_homeappliance_number"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await update_entity(mock_appliance.entities["Test.Number"], {"value": 0})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state
    assert state.state == "0"

    await update_entity(mock_appliance.entities["Test.Number"], {"value": 10})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "10"

    await update_entity(
        mock_appliance.entities["Test.Number"], {"min": 10, "max": 50, "stepSize": 5}
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.attributes[ATTR_MIN] == 10
    assert state.attributes[ATTR_MAX] == 50
    assert state.attributes[ATTR_STEP] == 5


async def test_set_value(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_entity_description: None,
) -> None:
    """Test setting a value."""
    entity_id = "number.fake_brand_homeappliance_number"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: "2"},
        blocking=True,
    )
    mock_appliance.session.request.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 204, "value": 2}],
        )
    )


async def test_native_value_cleared_when_expected_offline() -> None:
    """Stale program-duration values clear instead of showing a frozen number."""
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=True),
    )
    entity_description = HCNumberEntityDescription(
        key="number_duration", clear_on_expected_offline=True
    )
    entity = HCNumber(entity_description, runtime_data)

    assert entity.native_value is None


async def test_native_value_not_cleared_when_not_expected_offline() -> None:
    """The clearing only applies while actually expected_offline."""
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    appliance.entities["Test.Number"].value = 12960
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=False),
    )
    entity_description = HCNumberEntityDescription(
        key="number_duration", entity="Test.Number", clear_on_expected_offline=True
    )
    entity = HCNumber(entity_description, runtime_data)

    assert entity.native_value == 12960
