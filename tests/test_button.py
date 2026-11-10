"""Tests for button entity."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock, patch

import pytest
from custom_components import homeconnect_ws
from custom_components.homeconnect_ws import entity_descriptions
from custom_components.homeconnect_ws.const import DOMAIN
from custom_components.homeconnect_ws.entity_descriptions import HCButtonEntityDescription
from home_disconnect.entities import Access, Program
from home_disconnect.messages import Action, Message
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    CONF_DESCRIPTION,
    STATE_UNAVAILABLE,
    Platform,
)
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from . import appliance_class, make_appliance, setup_config_entry, setup_integration, update_entity
from .const import ENTITY_DESCRIPTIONS, MOCK_CONFIG_DATA, WASHER_CONFIG_DATA, WASHER_DESCRIPTION

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
    mock_appliance: Appliance,
    patch_entity_description: None,
) -> None:
    """Test pressing start button."""
    entity_id = "button.fake_brand_homeappliance_activeprogram"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await update_entity(mock_appliance.entities["Test.SelectedProgram"], {"value": 500})
    await hass.async_block_till_done()

    await hass.services.async_call(
        domain=BUTTON_DOMAIN,
        service=SERVICE_PRESS,
        service_data={ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_appliance.session.request.assert_awaited_once_with(
        Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data=[
                {
                    "program": 500,
                    # No option has a reported value yet, so none goes out -
                    # the appliance rejects {"value": null} entries with 400.
                    "options": [],
                }
            ],
        )
    )


async def test_start_full_option_set(
    hass: HomeAssistant,
    mock_appliance: Appliance,
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
    await update_entity(mock_appliance.entities["Test.SelectedProgram"], {"value": 500})
    await hass.async_block_till_done()

    with patch.object(Program, "full_option_set", new=True, create=True):
        await hass.services.async_call(
            domain=BUTTON_DOMAIN,
            service=SERVICE_PRESS,
            service_data={ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )

    mock_appliance.session.request.assert_awaited_once_with(
        Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data=[
                {
                    "program": 500,
                    "options": [],
                }
            ],
        )
    )


async def test_start_sends_known_values_but_skips_unavailable_options(
    hass: HomeAssistant,
    mock_appliance: Appliance,
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
    await update_entity(mock_appliance.entities["Test.Option1"], {"value": 1})
    await update_entity(mock_appliance.entities["Test.Option2"], {"value": 2, "available": False})
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await update_entity(mock_appliance.entities["Test.SelectedProgram"], {"value": 500})
    await hass.async_block_till_done()

    await hass.services.async_call(
        domain=BUTTON_DOMAIN,
        service=SERVICE_PRESS,
        service_data={ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_appliance.session.request.assert_awaited_once_with(
        Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data=[
                {
                    "program": 500,
                    "options": [{"uid": 401, "value": 1}],
                }
            ],
        )
    )


async def test_start_full_option_set_skips_unavailable_options(
    hass: HomeAssistant,
    mock_appliance: Appliance,
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
    await update_entity(mock_appliance.entities["Test.Option1"], {"min": 5})
    await update_entity(mock_appliance.entities["Test.Option2"], {"min": 1, "available": False})
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await update_entity(mock_appliance.entities["Test.SelectedProgram"], {"value": 500})
    await hass.async_block_till_done()

    with patch.object(Program, "full_option_set", new=True, create=True):
        await hass.services.async_call(
            domain=BUTTON_DOMAIN,
            service=SERVICE_PRESS,
            service_data={ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )

    mock_appliance.session.request.assert_awaited_once_with(
        Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data=[
                {
                    "program": 500,
                    "options": [{"uid": 401, "value": 5}],
                }
            ],
        )
    )


async def test_start_available_for_select_only_program(
    hass: HomeAssistant,
    mock_appliance: Appliance,
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
    await update_entity(mock_appliance.entities["Test.SelectedProgram"], {"value": 506})
    await hass.async_block_till_done()

    await hass.services.async_call(
        domain=BUTTON_DOMAIN,
        service=SERVICE_PRESS,
        service_data={ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_appliance.session.request.assert_awaited_once_with(
        Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data=[
                {
                    "program": 506,
                    # No option has a reported value yet, so none goes out -
                    # the appliance rejects {"value": null} entries with 400.
                    "options": [],
                }
            ],
        )
    )


async def test_start_stays_available_when_remote_start_not_allowed(
    hass: HomeAssistant,
    mock_appliance: Appliance,
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
    await update_entity(mock_appliance.entities["Test.SelectedProgram"], {"value": 500})
    await update_entity(
        mock_appliance.entities["BSH.Common.Status.RemoteControlStartAllowed"], {"value": False}
    )
    # The appliance also turns ActiveProgram read-only while it refuses a start,
    # which is the change the button's callback sees.
    await update_entity(mock_appliance.entities["Test.ActiveProgram"], {"access": "read"})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state
    assert state.state != "unavailable"


async def test_start_raises_when_remote_start_not_allowed(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_entity_description: None,
) -> None:
    """Pressing start while remote start isn't allowed must error, not silently no-op."""
    entity_id = "button.fake_brand_homeappliance_activeprogram"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await update_entity(mock_appliance.entities["Test.SelectedProgram"], {"value": 500})
    await update_entity(
        mock_appliance.entities["BSH.Common.Status.RemoteControlStartAllowed"], {"value": False}
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
    mock_appliance.session.request.assert_not_awaited()


async def test_start_proceeds_when_blocked_for_a_different_reason(
    hass: HomeAssistant,
    mock_appliance: Appliance,
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
    await update_entity(mock_appliance.entities["Test.SelectedProgram"], {"value": 500})
    await update_entity(
        mock_appliance.entities["BSH.Common.Status.RemoteControlStartAllowed"], {"value": True}
    )
    await update_entity(mock_appliance.entities["Test.ActiveProgram"], {"access": "read"})
    await hass.async_block_till_done()

    await hass.services.async_call(
        domain=BUTTON_DOMAIN,
        service=SERVICE_PRESS,
        service_data={ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    mock_appliance.session.request.assert_awaited_once()


async def test_abort(
    hass: HomeAssistant,
    mock_appliance: Appliance,
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

    mock_appliance.session.request.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 300, "value": True}],
        )
    )


async def test_press_runs_press_fn(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A button backed by a Setting does its own write instead of writing True.

    Commands take a bare True, but a Setting-backed button (BSH.Common.Setting
    .ApplianceDateTime, the appliance clock) has to send an actual value,
    computed when the button is pressed.
    """
    descriptions = {
        **ENTITY_DESCRIPTIONS,
        "button": [
            HCButtonEntityDescription(
                key="Test.Switch",
                name="ValueButton",
                entity="Test.Switch",
                press_fn=lambda appliance: appliance.set_values_raw(
                    {"Test.Switch": "2026-09-24T10:36:09"}
                ),
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

    mock_appliance.session.request.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 201, "value": "2026-09-24T10:36:09"}],
        )
    )


async def test_read_only_button_is_unavailable(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A button whose Setting the appliance locks read-only goes unavailable.

    Unlike a locked switch or select there is no value to keep showing, so a
    read-only button (e.g. the clock button while "Synchronize time with
    server" is on) is unavailable rather than pressable-then-error, and
    carries no readonly attribute. The Start button keeps its own rules.
    """
    descriptions = {
        **ENTITY_DESCRIPTIONS,
        "button": [
            HCButtonEntityDescription(
                key="Test.Switch",
                name="ValueButton",
                entity="Test.Switch",
                press_fn=lambda appliance: appliance.set_values_raw(
                    {"Test.Switch": "2026-09-24T10:36:09"}
                ),
            )
        ],
    }
    for module in (entity_descriptions, homeconnect_ws):
        monkeypatch.setattr(module, "get_available_entities", Mock(return_value=descriptions))
    entity_id = "button.fake_brand_homeappliance_valuebutton"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    state = hass.states.get(entity_id)
    assert state.state != STATE_UNAVAILABLE
    assert "readonly" not in state.attributes

    await update_entity(mock_appliance.entities["Test.Switch"], {"access": "read"})
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    await update_entity(mock_appliance.entities["Test.Switch"], {"access": "readWrite"})
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state != STATE_UNAVAILABLE


ACKNOWLEDGE_ENTITY_ID = "button.fake_brand_washer_acknowledge_program_message"


def _washer_with_acknowledge(finished_handling: str = "acknowledge") -> dict[str, Any]:
    """Return a washer's description with its end-of-program events, as on a WGB256A41."""
    description = deepcopy(WASHER_DESCRIPTION)
    description["event"] = [
        {
            "uid": uid,
            "name": f"BSH.Common.Event.{name}",
            "handling": handling,
            "level": "hint",
            "enumeration": {"0": "Off", "1": "Present", "2": "Confirmed"},
        }
        for uid, name, handling in (
            (540, "ProgramFinished", finished_handling),
            (545, "ProgramAborted", "acknowledge"),
        )
    ]
    description["command"] = [
        {
            "uid": 6,
            "name": "BSH.Common.Command.AcknowledgeEvent",
            "available": True,
            "access": Access.WRITE_ONLY,
        }
    ]
    return description


async def _setup_washer(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, description: dict[str, Any]
) -> Appliance:
    appliance = make_appliance(description)
    monkeypatch.setattr(homeconnect_ws.coordinator, "Appliance", appliance_class(appliance))
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={**WASHER_CONFIG_DATA, CONF_DESCRIPTION: description},
        unique_id=WASHER_CONFIG_DATA["device_id"],
    )
    with patch("custom_components.homeconnect_ws.PLATFORMS", [Platform.BUTTON]):
        await setup_integration(hass, config_entry)
    return appliance


@pytest.mark.parametrize(("uid", "other"), [(540, 545), (545, 540)])
async def test_acknowledge_program_message(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, uid: int, other: int
) -> None:
    """Test the button acknowledges the event that's showing, and only while one is."""
    appliance = await _setup_washer(hass, monkeypatch, _washer_with_acknowledge())
    assert hass.states.get(ACKNOWLEDGE_ENTITY_ID).state == STATE_UNAVAILABLE

    await update_entity(appliance.entities.by_uid[other], {"value": 0})
    await update_entity(appliance.entities.by_uid[uid], {"value": 1})
    await hass.async_block_till_done()
    assert hass.states.get(ACKNOWLEDGE_ENTITY_ID).state != STATE_UNAVAILABLE

    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: ACKNOWLEDGE_ENTITY_ID}, blocking=True
    )
    appliance.session.request.assert_awaited_once_with(
        Message(resource="/ro/values", action=Action.POST, data=[{"uid": 6, "value": uid}])
    )

    await update_entity(appliance.entities.by_uid[uid], {"value": 0})
    await hass.async_block_till_done()
    assert hass.states.get(ACKNOWLEDGE_ENTITY_ID).state == STATE_UNAVAILABLE


async def test_acknowledge_skips_events_that_dont_ask_for_it(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test a finished message that needs no acknowledging doesn't enable the button."""
    appliance = await _setup_washer(hass, monkeypatch, _washer_with_acknowledge("none"))

    await update_entity(appliance.entities.by_uid[540], {"value": 1})
    await hass.async_block_till_done()

    assert hass.states.get(ACKNOWLEDGE_ENTITY_ID).state == STATE_UNAVAILABLE


@pytest.mark.parametrize(
    "removed",
    [{"event": []}, {"command": []}],
    ids=["no_events", "no_command"],
)
async def test_no_acknowledge_button(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, removed: dict[str, list[Any]]
) -> None:
    """Test appliances without the command or the events don't get the button."""
    await _setup_washer(hass, monkeypatch, _washer_with_acknowledge() | removed)

    assert hass.states.get(ACKNOWLEDGE_ENTITY_ID) is None
