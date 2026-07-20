"""Tests for sensor entity."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from custom_components.homeconnect_ws import HCData
from custom_components.homeconnect_ws.entity_descriptions.descriptions_definitions import (
    HCSensorEntityDescription,
)
from custom_components.homeconnect_ws.sensor import HCWiFI
from homeassistant.components.sensor import ATTR_OPTIONS
from homeassistant.const import ATTR_FRIENDLY_NAME

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

    state = hass.states.get("sensor.fake_brand_homeappliance_sensor")
    assert state
    assert state.name == "Fake_brand HomeAppliance Sensor"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Fake_brand HomeAppliance Sensor"

    state = hass.states.get("sensor.fake_brand_homeappliance_sensor_enum")
    assert state
    assert state.name == "Fake_brand HomeAppliance Sensor.Enum"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Fake_brand HomeAppliance Sensor.Enum"
    assert state.attributes[ATTR_OPTIONS] == ["Off", "On"]

    state = hass.states.get("sensor.fake_brand_homeappliance_sensor_event")
    assert state
    assert state.name == "Fake_brand HomeAppliance Sensor.Event"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Fake_brand HomeAppliance Sensor.Event"
    assert state.attributes[ATTR_OPTIONS] == ["Event2", "Event1", "No Event"]

    state = hass.states.get("sensor.fake_brand_homeappliance_activeprogram")
    assert state
    assert state.name == "Fake_brand HomeAppliance ActiveProgram"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Fake_brand HomeAppliance ActiveProgram"
    assert state.attributes[ATTR_OPTIONS] == [
        "Named Favorite",
        "favorite_002",
        "test_program_program1",
        "test_program_program2",
    ]


async def test_update(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """Test updating entity."""
    entity_id = "sensor.fake_brand_homeappliance_sensor"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await mock_appliance.entities["Test.Sensor"].update({"value": 5})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "5"


async def test_update_enum(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """Test updating entity with enum."""
    entity_id = "sensor.fake_brand_homeappliance_sensor_enum"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await mock_appliance.entities["Test.Sensor.Enum"].update({"value": 0})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "Off"

    await mock_appliance.entities["Test.Sensor.Enum"].update({"value": 1})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "On"


async def test_update_event(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """Test updating event sensor."""
    entity_id = "sensor.fake_brand_homeappliance_sensor_event"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await mock_appliance.entities["Test.Event1"].update({"value": 0})
    await mock_appliance.entities["Test.Event2"].update({"value": 0})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "No Event"

    await mock_appliance.entities["Test.Event1"].update({"value": 1})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "Event1"

    await mock_appliance.entities["Test.Event2"].update({"value": 1})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "Event2"

    await mock_appliance.entities["Test.Event2"].update({"value": 0})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "Event1"


async def test_update_active_program(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """Test updating active program entity."""
    entity_id = "sensor.fake_brand_homeappliance_activeprogram"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await mock_appliance.entities["Test.ActiveProgram"].update({"value": 500})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "test_program_program1"

    await mock_appliance.entities["Test.ActiveProgram"].update({"value": 502})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "Named Favorite"


async def test_wifi_update_skips_when_not_connected() -> None:
    """
    WiFi polling must not attempt a request before the appliance has connected.

    Entities can be added (and HCWiFI's immediate poll-on-add fired) before the
    appliance's first handshake completes, since setup doesn't block on a
    successful connection. Polling anyway used to crash deep in
    home_disconnect's message-ID counter, which is only initialized once the
    handshake finishes.
    """
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    appliance.session.connected = False
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(),
    )
    entity_description = HCSensorEntityDescription(key="sensor_wifi_signal_strength")
    entity = HCWiFI(entity_description, runtime_data)

    await entity.async_update()

    assert entity.native_value is None
    appliance.get_network_config.assert_not_called()
