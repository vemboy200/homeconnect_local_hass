"""Tests for light entity."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import call

from home_disconnect.message import Action, Message
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT,
    ATTR_COLOR_MODE,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ATTR_SUPPORTED_COLOR_MODES,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    ColorMode,
)
from homeassistant.components.light import (
    DOMAIN as LIGHT_DOMAIN,
)
from homeassistant.components.light.const import DEFAULT_MAX_KELVIN, DEFAULT_MIN_KELVIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
)
from homeassistant.util.color import value_to_brightness

from . import setup_config_entry
from .const import MOCK_CONFIG_DATA

if TYPE_CHECKING:
    import pytest
    from home_disconnect.testutils import MockAppliance
    from homeassistant.core import HomeAssistant


async def test_setup(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test setting up entity."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.Lighting"].update({"value": True})
    await hass.async_block_till_done()

    state = hass.states.get("light.fake_brand_homeappliance_light_1")
    assert state
    assert state.name == "Fake_brand HomeAppliance Light.1"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Fake_brand HomeAppliance Light.1"
    assert state.attributes[ATTR_COLOR_MODE] == ColorMode.ONOFF
    assert state.attributes[ATTR_SUPPORTED_COLOR_MODES] == [ColorMode.ONOFF]

    state = hass.states.get("light.fake_brand_homeappliance_light_2")
    assert state
    assert state.name == "Fake_brand HomeAppliance Light.2"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Fake_brand HomeAppliance Light.2"
    assert state.attributes[ATTR_COLOR_MODE] == ColorMode.BRIGHTNESS
    assert state.attributes[ATTR_SUPPORTED_COLOR_MODES] == [ColorMode.BRIGHTNESS]

    state = hass.states.get("light.fake_brand_homeappliance_light_3")
    assert state
    assert state.name == "Fake_brand HomeAppliance Light.3"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Fake_brand HomeAppliance Light.3"
    assert state.attributes[ATTR_COLOR_MODE] == ColorMode.COLOR_TEMP
    assert state.attributes[ATTR_SUPPORTED_COLOR_MODES] == [ColorMode.COLOR_TEMP]

    state = hass.states.get("light.fake_brand_homeappliance_light_4")
    assert state
    assert state.name == "Fake_brand HomeAppliance Light.4"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Fake_brand HomeAppliance Light.4"
    assert state.attributes[ATTR_COLOR_MODE] == ColorMode.RGB
    assert state.attributes[ATTR_SUPPORTED_COLOR_MODES] == [ColorMode.RGB]


async def test_update_on_off(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test On/Off."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    # No value reported yet: unknown, not off.
    state = hass.states.get("light.fake_brand_homeappliance_light_1")
    assert state.state == STATE_UNKNOWN

    await mock_appliance.entities["Test.Lighting"].update({"value": True})
    await hass.async_block_till_done()

    state = hass.states.get("light.fake_brand_homeappliance_light_1")
    assert state.state == STATE_ON

    await mock_appliance.entities["Test.Lighting"].update({"value": False})
    await hass.async_block_till_done()

    state = hass.states.get("light.fake_brand_homeappliance_light_1")
    assert state.state == STATE_OFF


async def test_on(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test Set On/Off."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.Lighting"].update({"value": False})
    await hass.async_block_till_done()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_1",
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 108, "value": True}],
        )
    )


async def test_off(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test Set Off."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.Lighting"].update({"value": True})
    await hass.async_block_till_done()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_OFF,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_1",
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data={"uid": 108, "value": False},
        )
    )


async def test_update_brightness(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test Brightness."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.Lighting"].update({"value": True})
    await mock_appliance.entities["Test.LightingBrightness"].update({"value": 100})
    await hass.async_block_till_done()

    state = hass.states.get("light.fake_brand_homeappliance_light_2")
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == 255  # 100%

    await mock_appliance.entities["Test.LightingBrightness"].update({"value": 2})
    await hass.async_block_till_done()

    state = hass.states.get("light.fake_brand_homeappliance_light_2")
    assert state.attributes[ATTR_BRIGHTNESS] == 5  # 2%

    await mock_appliance.entities["Test.LightingBrightness"].update({"value": 50})
    await hass.async_block_till_done()

    state = hass.states.get("light.fake_brand_homeappliance_light_2")
    assert state.attributes[ATTR_BRIGHTNESS] == 128  # 50%

    await mock_appliance.entities["Test.LightingBrightness"].update({"value": 3})
    await hass.async_block_till_done()

    state = hass.states.get("light.fake_brand_homeappliance_light_2")
    assert state.attributes[ATTR_BRIGHTNESS] == 8  # 3%


async def test_available_when_brightness_unavailable(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """
    On/off stays usable even if a secondary capability isn't currently readable.

    Confirmed live on fork issue #15 (Bosch DWK91LT60): brightness is only
    reported available while the light itself is on, so gating the whole
    entity's availability on it created a deadlock - the light couldn't be
    turned on because it was unavailable, and it was unavailable because
    brightness (which only becomes available once on) wasn't set yet.
    """
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.Lighting"].update({"value": False})
    await mock_appliance.entities["Test.LightingBrightness"].update({"available": False})
    await hass.async_block_till_done()

    state = hass.states.get("light.fake_brand_homeappliance_light_2")
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_BRIGHTNESS] is None

    await mock_appliance.entities["Test.Lighting"].update({"value": True})
    await mock_appliance.entities["Test.LightingBrightness"].update(
        {"available": True, "value": 100}
    )
    await hass.async_block_till_done()

    state = hass.states.get("light.fake_brand_homeappliance_light_2")
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == 255


async def test_set_brightness(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test Brightness."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.Lighting"].update({"value": True})
    await mock_appliance.entities["Test.LightingBrightness"].update({"value": 2})
    await hass.async_block_till_done()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_2",
            ATTR_BRIGHTNESS_PCT: 100,
        },
        blocking=True,
    )
    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 109, "value": 100}],
        )
    )
    mock_appliance.session.send_sync.reset_mock()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_2",
            ATTR_BRIGHTNESS_PCT: 50,
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 109, "value": 50}],
        )
    )
    mock_appliance.session.send_sync.reset_mock()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_2",
            ATTR_BRIGHTNESS_PCT: 2,
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 109, "value": 2}],
        )
    )
    mock_appliance.session.send_sync.reset_mock()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_2",
            ATTR_BRIGHTNESS_PCT: 1,
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 109, "value": 2}],
        )
    )
    mock_appliance.session.send_sync.reset_mock()


async def test_update_color_temp(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test Color temp."""
    mock_appliance.entities.pop("Cooking.Hood.Setting.ColorTemperature")
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.Lighting"].update({"value": True})
    await mock_appliance.entities["Test.LightingBrightness"].update({"value": 100})
    await mock_appliance.entities["Test.LightingColorTempPercent"].update({"value": 100})
    await hass.async_block_till_done()

    state = hass.states.get("light.fake_brand_homeappliance_light_3")
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == 255  # 100%
    assert state.attributes[ATTR_COLOR_TEMP_KELVIN] == DEFAULT_MAX_KELVIN  # 100%

    await mock_appliance.entities["Test.LightingColorTempPercent"].update({"value": 0})
    await hass.async_block_till_done()

    state = hass.states.get("light.fake_brand_homeappliance_light_3")
    assert state.attributes[ATTR_COLOR_TEMP_KELVIN] == DEFAULT_MIN_KELVIN  # 0%

    await mock_appliance.entities["Test.LightingColorTempPercent"].update({"value": 50})
    await hass.async_block_till_done()

    state = hass.states.get("light.fake_brand_homeappliance_light_3")
    assert state.attributes[ATTR_COLOR_TEMP_KELVIN] == 4267  # 50%


async def test_set_color_temp(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test Color temp."""
    mock_appliance.entities.pop("Cooking.Hood.Setting.ColorTemperature")
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.Lighting"].update({"value": True})
    await mock_appliance.entities["Test.LightingBrightness"].update({"value": 100})
    await mock_appliance.entities["Test.LightingColorTempPercent"].update({"value": 0})
    await hass.async_block_till_done()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_3",
            ATTR_COLOR_TEMP_KELVIN: DEFAULT_MAX_KELVIN,
        },
        blocking=True,
    )
    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 110, "value": 100}],
        )
    )
    mock_appliance.session.send_sync.reset_mock()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_3",
            ATTR_COLOR_TEMP_KELVIN: DEFAULT_MIN_KELVIN,
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 110, "value": 0}],
        )
    )
    mock_appliance.session.send_sync.reset_mock()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_3",
            ATTR_COLOR_TEMP_KELVIN: 4268,
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 110, "value": 50}],
        )
    )
    mock_appliance.session.send_sync.reset_mock()


async def test_set_brightness_color_temp(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test Brightness and Color temp."""
    mock_appliance.entities.pop("Cooking.Hood.Setting.ColorTemperature")
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.Lighting"].update({"value": False})
    await mock_appliance.entities["Test.LightingBrightness"].update({"value": 0})
    await mock_appliance.entities["Test.LightingColorTempPercent"].update({"value": 0})
    await hass.async_block_till_done()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_3",
            ATTR_BRIGHTNESS_PCT: 100,
            ATTR_COLOR_TEMP_KELVIN: DEFAULT_MAX_KELVIN,
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_has_awaits(
        [
            call(
                Message(
                    resource="/ro/values",
                    action=Action.POST,
                    data=[{"uid": 108, "value": True}],
                )
            ),
            call(
                Message(
                    resource="/ro/values",
                    action=Action.POST,
                    data=[
                        {"uid": 109, "value": 100},
                        {"uid": 110, "value": 100},
                    ],
                )
            ),
        ]
    )
    mock_appliance.session.send_sync.reset_mock()

    await mock_appliance.entities["Test.Lighting"].update({"value": True})
    await mock_appliance.entities["Test.LightingBrightness"].update({"value": 100})
    await mock_appliance.entities["Test.LightingColorTempPercent"].update({"value": 100})
    await hass.async_block_till_done()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_3",
            ATTR_BRIGHTNESS_PCT: 2,
            ATTR_COLOR_TEMP_KELVIN: DEFAULT_MIN_KELVIN,
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[
                {"uid": 109, "value": 2},
                {"uid": 110, "value": 0},
            ],
        )
    )


async def test_update_color_temp_inverted(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test Color temp."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.Lighting"].update({"value": True})
    await mock_appliance.entities["Test.LightingBrightness"].update({"value": 100})
    await mock_appliance.entities["Test.LightingColorTempPercent"].update({"value": 0})
    await hass.async_block_till_done()

    state = hass.states.get("light.fake_brand_homeappliance_light_3")
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == 255  # 100%
    assert state.attributes[ATTR_COLOR_TEMP_KELVIN] == DEFAULT_MAX_KELVIN  # 0%

    await mock_appliance.entities["Test.LightingColorTempPercent"].update({"value": 100})
    await hass.async_block_till_done()

    state = hass.states.get("light.fake_brand_homeappliance_light_3")
    assert state.attributes[ATTR_COLOR_TEMP_KELVIN] == DEFAULT_MIN_KELVIN  # 100%

    await mock_appliance.entities["Test.LightingColorTempPercent"].update({"value": 50})
    await hass.async_block_till_done()

    state = hass.states.get("light.fake_brand_homeappliance_light_3")
    assert state.attributes[ATTR_COLOR_TEMP_KELVIN] == 4267  # 50%


async def test_set_color_temp_inverted(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test Color temp."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.Lighting"].update({"value": True})
    await mock_appliance.entities["Test.LightingBrightness"].update({"value": 100})
    await mock_appliance.entities["Test.LightingColorTempPercent"].update({"value": 100})
    await hass.async_block_till_done()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_3",
            ATTR_COLOR_TEMP_KELVIN: DEFAULT_MAX_KELVIN,
        },
        blocking=True,
    )
    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 113, "value": 0}, {"uid": 110, "value": 0}],
        )
    )
    mock_appliance.session.send_sync.reset_mock()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_3",
            ATTR_COLOR_TEMP_KELVIN: DEFAULT_MIN_KELVIN,
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 113, "value": 0}, {"uid": 110, "value": 100}],
        )
    )
    mock_appliance.session.send_sync.reset_mock()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_3",
            ATTR_COLOR_TEMP_KELVIN: 4267,
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 113, "value": 0}, {"uid": 110, "value": 50}],
        )
    )
    mock_appliance.session.send_sync.reset_mock()


async def test_set_brightness_color_temp_inverted(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test Brightness and Color temp."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.Lighting"].update({"value": False})
    await mock_appliance.entities["Test.LightingBrightness"].update({"value": 0})
    await mock_appliance.entities["Test.LightingColorTempPercent"].update({"value": 0})
    await hass.async_block_till_done()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_3",
            ATTR_BRIGHTNESS_PCT: 100,
            ATTR_COLOR_TEMP_KELVIN: DEFAULT_MAX_KELVIN,
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_has_awaits(
        [
            call(
                Message(
                    resource="/ro/values",
                    action=Action.POST,
                    data=[{"uid": 108, "value": True}],
                )
            ),
            call(
                Message(
                    resource="/ro/values",
                    action=Action.POST,
                    data=[
                        {"uid": 109, "value": 100},
                        {"uid": 113, "value": 0},
                        {"uid": 110, "value": 0},
                    ],
                )
            ),
        ]
    )
    mock_appliance.session.send_sync.reset_mock()

    await mock_appliance.entities["Test.Lighting"].update({"value": True})
    await mock_appliance.entities["Test.LightingBrightness"].update({"value": 100})
    await mock_appliance.entities["Test.LightingColorTempPercent"].update({"value": 0})
    await hass.async_block_till_done()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_3",
            ATTR_BRIGHTNESS_PCT: 2,
            ATTR_COLOR_TEMP_KELVIN: DEFAULT_MIN_KELVIN,
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[
                {"uid": 109, "value": 2},
                {"uid": 113, "value": 0},
                {"uid": 110, "value": 100},
            ],
        )
    )


async def test_update_color(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test update RGB."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.Lighting"].update({"value": True})
    await mock_appliance.entities["Test.LightingCustomColor"].update({"value": "#ff0000"})
    await mock_appliance.entities["Test.LightingColor"].update({"value": 1})
    await hass.async_block_till_done()

    state = hass.states.get("light.fake_brand_homeappliance_light_4")
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == 255  # 100%
    assert state.attributes[ATTR_RGB_COLOR] == (255, 0, 0)

    await mock_appliance.entities["Test.LightingCustomColor"].update({"value": "#7f0000"})
    await hass.async_block_till_done()

    state = hass.states.get("light.fake_brand_homeappliance_light_4")
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == 127  # 100%
    assert state.attributes[ATTR_RGB_COLOR] == (255, 0, 0)


async def test_set_color(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test set RGB."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.Lighting"].update({"value": True})
    await mock_appliance.entities["Test.LightingCustomColor"].update({"value": "#ff0000"})
    await mock_appliance.entities["Test.LightingColor"].update({"value": 1})
    await hass.async_block_till_done()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_4",
            ATTR_BRIGHTNESS: 127,
        },
        blocking=True,
    )
    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 111, "value": "#7f0000"}],
        )
    )
    mock_appliance.session.send_sync.reset_mock()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_4",
            ATTR_RGB_COLOR: (0, 255, 0),
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 111, "value": "#00ff00"}],
        )
    )
    mock_appliance.session.send_sync.reset_mock()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_4",
            ATTR_RGB_COLOR: (0, 255, 0),
            ATTR_BRIGHTNESS_PCT: 50,
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 111, "value": "#008000"}],
        )
    )
    mock_appliance.session.send_sync.reset_mock()

    await mock_appliance.entities["Test.LightingCustomColor"].update({"value": "#800000"})
    await hass.async_block_till_done()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_4",
            ATTR_RGB_COLOR: (0, 0, 255),
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 111, "value": "#000080"}],
        )
    )
    mock_appliance.session.send_sync.reset_mock()

    # A preset color is active: a brightness-only change writes the preset's
    # own brightness Setting and keeps the preset, instead of switching to
    # CustomColor and replacing it with the last custom color.
    await mock_appliance.entities["Test.LightingColor"].update({"value": 33})
    await mock_appliance.entities["Test.LightingBrightness"].update({"value": 80})
    await hass.async_block_till_done()

    state = hass.states.get("light.fake_brand_homeappliance_light_4")
    assert state.attributes[ATTR_BRIGHTNESS] == value_to_brightness((1, 100), 80)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_4",
            ATTR_BRIGHTNESS_PCT: 50,
        },
        blocking=True,
    )
    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 109, "value": 50}],
        )
    )
    mock_appliance.session.send_sync.reset_mock()

    # Picking a color on a preset still switches to CustomColor.
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_4",
            ATTR_RGB_COLOR: (255, 0, 0),
            ATTR_BRIGHTNESS: 255,
        },
        blocking=True,
    )
    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 111, "value": "#ff0000"}, {"uid": 112, "value": 1}],
        )
    )
    mock_appliance.session.send_sync.reset_mock()


async def test_turn_on_skips_color_write_when_color_setting_unavailable(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A color write must not be attempted while the color Setting is unavailable.

    Confirmed on upstream issue #477 (Siemens LC91KWW60 ambient light):
    the color Setting is only reported available while the light itself is
    on, so writing a color before that - e.g. the light's very first
    turn_on - hits a Setting the appliance rejects with WriteRequest
    NotAvailable. Turning the light on should still work, just without a
    color write, rather than raising or errouring against the appliance.
    """
    monkeypatch.setattr("custom_components.homeconnect_ws.light._RGB_AVAILABLE_TIMEOUT", 0.05)
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.Lighting"].update({"value": False})
    # While off, the hood reports both the color mode and the custom color
    # Settings as unavailable (descriptionChange for 589/590 on #477).
    await mock_appliance.entities["Test.LightingColor"].update({"available": False})
    await mock_appliance.entities["Test.LightingCustomColor"].update({"available": False})
    await hass.async_block_till_done()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_4",
            ATTR_RGB_COLOR: (0, 255, 0),
            ATTR_BRIGHTNESS: 127,
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 108, "value": True}],
        )
    )


async def test_turn_on_when_brightness_has_no_value(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test turning on while the appliance reports no brightness value."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    # The appliance drops the brightness value while the light is off. The
    # entity cannot be updated to None, so clear it the way a never-received
    # value leaves it.
    await mock_appliance.entities["Test.Lighting"].update({"value": False})
    mock_appliance.entities["Test.LightingBrightness"]._value = None
    await hass.async_block_till_done()

    state = hass.states.get("light.fake_brand_homeappliance_light_2")
    assert state
    assert state.attributes[ATTR_BRIGHTNESS] is None

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_2",
            ATTR_BRIGHTNESS_PCT: 100,
        },
        blocking=True,
    )
    mock_appliance.session.send_sync.assert_has_awaits(
        [
            call(
                Message(
                    resource="/ro/values",
                    action=Action.POST,
                    data=[{"uid": 108, "value": True}],
                )
            ),
            call(
                Message(
                    resource="/ro/values",
                    action=Action.POST,
                    data=[{"uid": 109, "value": 100}],
                )
            ),
        ]
    )
    mock_appliance.session.send_sync.reset_mock()


async def test_turn_on_sends_power_and_color_as_separate_messages(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """
    Power-on must not be bundled into the same write as color/brightness.

    Confirmed on upstream issue #477 (Siemens LC91KWW60/04 ambient light):
    the appliance accepts a bare power-on write but rejects the combined
    form with WriteRequest NotAvailable, so the whole turn_on fails - not
    just the color part.
    """
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.Lighting"].update({"value": False})
    await mock_appliance.entities["Test.LightingColor"].update({"value": 1})
    await hass.async_block_till_done()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_4",
            ATTR_RGB_COLOR: (0, 255, 0),
            ATTR_BRIGHTNESS: 255,
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_has_awaits(
        [
            call(
                Message(
                    resource="/ro/values",
                    action=Action.POST,
                    data=[{"uid": 108, "value": True}],
                )
            ),
            call(
                Message(
                    resource="/ro/values",
                    action=Action.POST,
                    data=[{"uid": 111, "value": "#00ff00"}],
                )
            ),
        ]
    )


async def test_turn_on_writes_color_once_available_after_power_on(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """
    A color picked while the light is off must still be written.

    Confirmed on upstream issue #477 (Siemens LC91KWW60/04 ambient light):
    the color Settings are reported unavailable while the light is off and
    flip to available via a descriptionChange NOTIFY ~60 ms after the
    power-on write is acknowledged. turn_on must wait for that instead of
    dropping the color.
    """
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.Lighting"].update({"value": False})
    await mock_appliance.entities["Test.LightingColor"].update({"value": 1})
    await mock_appliance.entities["Test.LightingCustomColor"].update({"available": False})
    await hass.async_block_till_done()

    color_entity = mock_appliance.entities["Test.LightingCustomColor"]

    async def _appliance_reacts(message: Message) -> None:
        if message.data == [{"uid": 108, "value": True}]:
            hass.async_create_task(color_entity.update({"available": True}))

    mock_appliance.session.send_sync.side_effect = _appliance_reacts

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_4",
            ATTR_RGB_COLOR: (0, 255, 0),
            ATTR_BRIGHTNESS: 255,
        },
        blocking=True,
    )

    assert mock_appliance.session.send_sync.await_args_list == [
        call(
            Message(
                resource="/ro/values",
                action=Action.POST,
                data=[{"uid": 108, "value": True}],
            )
        ),
        call(
            Message(
                resource="/ro/values",
                action=Action.POST,
                data=[{"uid": 111, "value": "#00ff00"}],
            )
        ),
    ]


async def test_plain_turn_on_does_not_wait_for_color(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A turn_on without color or brightness must not wait for the color Setting.

    The appliance restores its last color on power-on, so there is nothing to
    write - and an appliance whose color Setting never becomes available must
    not stall every plain turn-on.
    """

    async def _must_not_wait(*_: object) -> None:
        msg = "plain turn_on must not wait for the color Setting"
        raise AssertionError(msg)

    monkeypatch.setattr(
        "custom_components.homeconnect_ws.light.HCLight._wait_until", _must_not_wait
    )
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.Lighting"].update({"value": False})
    await mock_appliance.entities["Test.LightingCustomColor"].update({"available": False})
    await hass.async_block_till_done()

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_4"},
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 108, "value": True}],
        )
    )


async def test_set_color_from_preset_switches_mode_first(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """
    Picking a custom color while a preset color is active must work.

    Confirmed live on upstream issue #477 (Siemens LC91KWW60/04): with a preset
    color active, the hood offers the color mode Setting but not the custom
    color Setting at all; the custom color only becomes available once the
    mode is switched to CustomColor. Without switching first, no color write
    was sent at all.
    """
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.Lighting"].update({"value": True})
    await mock_appliance.entities["Test.LightingColor"].update({"value": 33})
    await mock_appliance.entities["Test.LightingCustomColor"].update({"available": False})
    await hass.async_block_till_done()

    color_entity = mock_appliance.entities["Test.LightingCustomColor"]
    mode_entity = mock_appliance.entities["Test.LightingColor"]

    async def _appliance_reacts(message: Message) -> None:
        if message.data == [{"uid": 112, "value": 1}]:
            await mode_entity.update({"value": 1})
            hass.async_create_task(color_entity.update({"available": True}))

    mock_appliance.session.send_sync.side_effect = _appliance_reacts

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.fake_brand_homeappliance_light_4",
            ATTR_RGB_COLOR: (0, 0, 255),
            ATTR_BRIGHTNESS: 255,
        },
        blocking=True,
    )

    assert mock_appliance.session.send_sync.await_args_list == [
        call(
            Message(
                resource="/ro/values",
                action=Action.POST,
                data=[{"uid": 112, "value": 1}],
            )
        ),
        call(
            Message(
                resource="/ro/values",
                action=Action.POST,
                data=[{"uid": 111, "value": "#0000ff"}],
            )
        ),
    ]
