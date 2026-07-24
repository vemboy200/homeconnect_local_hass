"""Tests for binary sensor entity."""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.homeconnect_ws.const import DOMAIN
from homeassistant.const import ATTR_FRIENDLY_NAME, STATE_OFF, STATE_ON, STATE_UNKNOWN

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

    state = hass.states.get("binary_sensor.fake_brand_homeappliance_binarysensor")
    assert state
    assert state.state == STATE_OFF
    assert state.name == "Fake_brand HomeAppliance BinarySensor"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Fake_brand HomeAppliance BinarySensor"

    state = hass.states.get("binary_sensor.fake_brand_homeappliance_binarysensor_enum")
    assert state
    assert state.state == STATE_UNKNOWN
    assert state.name == "Fake_brand HomeAppliance BinarySensor.Enum"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Fake_brand HomeAppliance BinarySensor.Enum"


async def test_update(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """Test updating entity."""
    entity_id = "binary_sensor.fake_brand_homeappliance_binarysensor"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await mock_appliance.entities["Test.BinarySensor"].update({"value": True})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_ON

    await mock_appliance.entities["Test.BinarySensor"].update({"value": False})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_OFF


async def test_connection_sensor_clean_disconnect_attribute(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """clean_disconnect reflects the most recent close code, not current connectivity."""
    entity_id = "binary_sensor.fake_brand_homeappliance_connection"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    mock_appliance.session.last_close_code = 1000
    entry.runtime_data.coordinator.async_set_updated_data(None)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state
    assert state.attributes["clean_disconnect"] is True

    mock_appliance.session.last_close_code = 1006
    entry.runtime_data.coordinator.async_set_updated_data(None)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.attributes["clean_disconnect"] is False


async def test_update_enum(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """Test updating entity with enum."""
    entity_id = "binary_sensor.fake_brand_homeappliance_binarysensor_enum"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await mock_appliance.entities["Test.BinarySensor.Enum"].update({"value": 0})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_OFF

    await mock_appliance.entities["Test.BinarySensor.Enum"].update({"value": 1})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
