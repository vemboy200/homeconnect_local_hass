"""Tests for button entity."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import pytest
from custom_components import homeconnect_ws
from custom_components.homeconnect_ws import entity_descriptions
from custom_components.homeconnect_ws.entity_descriptions import HCButtonEntityDescription
from home_disconnect.entities import Program
from home_disconnect.message import Action, Message
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID, ATTR_FRIENDLY_NAME
from homeassistant.exceptions import HomeAssistantError

from . import setup_config_entry
from .const import ENTITY_DESCRIPTIONS, MOCK_CONFIG_DATA

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

    state = hass.states.get("button.fake_brand_homeappliance_activeprogram")
    assert state
    assert state.name == "Fake_brand HomeAppliance ActiveProgram"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Fake_brand HomeAppliance ActiveProgram"

    state = hass.states.get("button.fake_brand_homeappliance_abortprogram")
    assert state
    assert state.name == "Fake_brand HomeAppliance AbortProgram"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Fake_brand HomeAppliance AbortProgram"


async def test_start(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test pressing start button."""
    entity_id = "button.fake_brand_homeappliance_activeprogram"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.SelectedProgram"].update({"value": 500})
    await hass.async_block_till_done()

    await hass.services.async_call(
        domain=BUTTON_DOMAIN,
        service=SERVICE_PRESS,
        service_data={ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data={
                "program": 500,
                # No option has a reported value yet, so none goes out -
                # the appliance rejects {"value": null} entries with 400.
                "options": [],
            },
        )
    )


async def test_start_full_option_set(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """
    Pressing start builds a well-formed option set for appliances that need one.

    Confirmed live on a Siemens CoffeeMaker and a NEFF oven: sending the raw
    (possibly None) shadow value of every option, like the plain start() call
    above does, gets rejected with a 400. Options with no value and no min
    (like these) are dropped entirely instead of sent as null.
    """
    entity_id = "button.fake_brand_homeappliance_activeprogram"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.SelectedProgram"].update({"value": 500})
    await hass.async_block_till_done()

    with patch.object(Program, "full_option_set", new=True, create=True):
        await hass.services.async_call(
            domain=BUTTON_DOMAIN,
            service=SERVICE_PRESS,
            service_data={ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data={
                "program": 500,
                "options": [],
            },
        )
    )


async def test_start_sends_known_values_but_skips_unavailable_options(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """
    Pressing start sends the options' known values, minus unavailable ones.

    Option1 has a reported value and goes out (a hood's Venting program needs
    its level, fork issue #14). Option2 has a value too, but the appliance has
    withdrawn it for this program (available: false) - a value for an option
    the appliance does not offer makes it reject the whole write with 400
    (Siemens EQ.9 CoffeeMaker, fork issue #97).
    """
    entity_id = "button.fake_brand_homeappliance_activeprogram"
    await mock_appliance.entities["Test.Option1"].update({"value": 1})
    await mock_appliance.entities["Test.Option2"].update({"value": 2, "available": False})
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.SelectedProgram"].update({"value": 500})
    await hass.async_block_till_done()

    await hass.services.async_call(
        domain=BUTTON_DOMAIN,
        service=SERVICE_PRESS,
        service_data={ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data={
                "program": 500,
                "options": [{"uid": 401, "value": 1}],
            },
        )
    )


async def test_start_full_option_set_skips_unavailable_options(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """
    The full option set leaves out options the appliance does not offer.

    Confirmed live on a Siemens EQ.9 CoffeeMaker (fork issue #97): DisplayName
    is listed on every beverage program with a min, but never reported or made
    available. Filling it from min like the other valueless options made the
    appliance reject every start with 400; without it the same write succeeds.
    """
    entity_id = "button.fake_brand_homeappliance_activeprogram"
    await mock_appliance.entities["Test.Option1"].update({"min": 5})
    await mock_appliance.entities["Test.Option2"].update({"min": 1, "available": False})
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.SelectedProgram"].update({"value": 500})
    await hass.async_block_till_done()

    with patch.object(Program, "full_option_set", new=True, create=True):
        await hass.services.async_call(
            domain=BUTTON_DOMAIN,
            service=SERVICE_PRESS,
            service_data={ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data={
                "program": 500,
                "options": [{"uid": 401, "value": 5}],
            },
        )
    )


async def test_start_available_for_select_only_program(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """
    The start button must work for SELECT_ONLY programs too, not just SELECT_AND_START.

    Confirmed live on fork issue #21: selecting a SELECT_ONLY program only
    stages it and its options (a write to SelectedProgram), it doesn't start
    anything - a separate write to ActiveProgram is what starts it, and the
    official cloud integration's own debug log showed exactly that as two
    distinct requests. Program.start() already posts to ActiveProgram
    unconditionally regardless of execution type, so this was a pure
    availability-gating bug, not a protocol one.
    """
    entity_id = "button.fake_brand_homeappliance_activeprogram"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.SelectedProgram"].update({"value": 506})
    await hass.async_block_till_done()

    await hass.services.async_call(
        domain=BUTTON_DOMAIN,
        service=SERVICE_PRESS,
        service_data={ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data={
                "program": 506,
                # No option has a reported value yet, so none goes out -
                # the appliance rejects {"value": null} entries with 400.
                "options": [],
            },
        )
    )


async def test_start_stays_available_when_remote_start_not_allowed(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """
    The start button must stay visible/pressable even when remote start is currently refused.

    BSH.Common.Status.RemoteControlStartAllowed can only ever be flipped by a
    human physically at the appliance - no client, local or cloud, can set it
    remotely. Gating the button's availability on it made an expected, common
    appliance state look like an integration bug instead of a silently
    greyed-out button. async_press() is responsible for surfacing that state
    instead (see the test below).
    """
    entity_id = "button.fake_brand_homeappliance_activeprogram"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.SelectedProgram"].update({"value": 500})
    await mock_appliance.entities["BSH.Common.Status.RemoteControlStartAllowed"].update(
        {"value": False}
    )
    # The button only registers a callback on its own entity (ActiveProgram), not
    # on SelectedProgram - nudge it so HA's cached state actually recomputes.
    await mock_appliance.entities["Test.ActiveProgram"].update({"access": "readwrite"})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state
    assert state.state != "unavailable"


async def test_start_raises_when_remote_start_not_allowed(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Pressing start while remote start isn't allowed must error, not silently no-op."""
    entity_id = "button.fake_brand_homeappliance_activeprogram"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.SelectedProgram"].update({"value": 500})
    await mock_appliance.entities["BSH.Common.Status.RemoteControlStartAllowed"].update(
        {"value": False}
    )
    await hass.async_block_till_done()

    with pytest.raises(HomeAssistantError) as exc_info:
        await hass.services.async_call(
            domain=BUTTON_DOMAIN,
            service=SERVICE_PRESS,
            service_data={ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )

    assert exc_info.value.translation_key == "remote_start_not_allowed"
    mock_appliance.session.send_sync.assert_not_awaited()


async def test_start_proceeds_when_blocked_for_a_different_reason(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """
    Pressing start while blocked for a non-remote-start reason must not misattribute it.

    ActiveProgram.access reflects whether the appliance can currently accept a
    start for *any* reason, not just remote-start confirmation - checking it
    directly (instead of BSH.Common.Status.RemoteControlStartAllowed) would
    wrongly tell a user to go press a physical button that can't fix an open
    door. Confirmed live: RemoteControlStartAllowed was already "on" but
    ActiveProgram.access was still "read" because the door was open, and the
    button incorrectly showed the remote-start message anyway before this fix.
    """
    entity_id = "button.fake_brand_homeappliance_activeprogram"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.SelectedProgram"].update({"value": 500})
    await mock_appliance.entities["BSH.Common.Status.RemoteControlStartAllowed"].update(
        {"value": True}
    )
    await mock_appliance.entities["Test.ActiveProgram"].update({"access": "read"})
    await hass.async_block_till_done()

    await hass.services.async_call(
        domain=BUTTON_DOMAIN,
        service=SERVICE_PRESS,
        service_data={ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once()


async def test_abort(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test pressing abort button."""
    entity_id = "button.fake_brand_homeappliance_abortprogram"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await hass.services.async_call(
        domain=BUTTON_DOMAIN,
        service=SERVICE_PRESS,
        service_data={ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data={"uid": 300, "value": True},
        )
    )


async def test_press_writes_value_from_press_value_fn(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A button backed by a Setting writes its own value instead of True.

    Commands take a bare True, but a Setting-backed button (BSH.Common.Setting
    .ApplianceDateTime, the appliance clock) has to send an actual value, and
    one that is computed when the button is pressed rather than when the
    entity description is built.
    """
    descriptions = {
        **ENTITY_DESCRIPTIONS,
        "button": [
            HCButtonEntityDescription(
                key="Test.Switch",
                name="ValueButton",
                entity="Test.Switch",
                press_value_fn=lambda: "2026-09-24T10:36:09",
            )
        ],
    }
    for module in (entity_descriptions, homeconnect_ws):
        monkeypatch.setattr(module, "get_available_entities", Mock(return_value=descriptions))
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await hass.services.async_call(
        domain=BUTTON_DOMAIN,
        service=SERVICE_PRESS,
        service_data={ATTR_ENTITY_ID: "button.fake_brand_homeappliance_valuebutton"},
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data={"uid": 201, "value": "2026-09-24T10:36:09"},
        )
    )
