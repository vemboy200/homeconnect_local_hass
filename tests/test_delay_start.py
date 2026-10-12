"""Tests for the "Delay start" select and how the Start button applies it."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from custom_components.homeconnect_ws.entity_descriptions.common import generate_delay_start
from custom_components.homeconnect_ws.helpers import (
    DELAY_START_NONE,
    DELAY_START_OPTIONS,
    ESTIMATED_TOTAL_PROGRAM_TIME,
    FINISH_IN_RELATIVE,
    START_IN_RELATIVE,
    DelayStart,
    apply_delay_start,
    delay_start_entity,
)
from home_disconnect.message import Action, Message
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.components.select import ATTR_OPTION, SERVICE_SELECT_OPTION
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import mock_restore_cache

from . import setup_config_entry
from .const import MOCK_CONFIG_DATA

if TYPE_CHECKING:
    from home_disconnect.testutils import MockAppliance
    from homeassistant.core import HomeAssistant

SELECT_ENTITY_ID = "select.fake_brand_homeappliance_delay_start"
START_ENTITY_ID = "button.fake_brand_homeappliance_activeprogram"


def _option(name: str, uid: int, value: int | None = None, max_value: int = 86400) -> MagicMock:
    option = MagicMock(uid=uid, value=value, max=max_value)
    option.name = name
    return option


def _appliance(*options: MagicMock) -> MagicMock:
    appliance = MagicMock()
    appliance.entities = {option.name: option for option in options}
    return appliance


def test_delay_start_seconds_and_reset() -> None:
    """The option maps to seconds, and reset() goes back to no delay and notifies."""
    delay_start = DelayStart()
    assert delay_start.seconds == 0
    delay_start.option = "3h"
    assert delay_start.seconds == 3 * 3600

    calls = []
    remove = delay_start.add_listener(lambda: calls.append(True))
    delay_start.reset()
    assert delay_start.option == DELAY_START_NONE
    assert calls == [True]

    remove()
    delay_start.reset()
    assert calls == [True]


def test_delay_start_options() -> None:
    """No delay plus whole hours up to 24 h."""
    assert DELAY_START_OPTIONS[0] == DELAY_START_NONE
    assert DELAY_START_OPTIONS[1:] == [f"{hours}h" for hours in range(1, 25)]


def test_delay_start_entity_prefers_start_in() -> None:
    """StartInRelative takes the delay as-is, so it wins over FinishInRelative."""
    start_in = _option(START_IN_RELATIVE, 550)
    finish_in = _option(FINISH_IN_RELATIVE, 551)
    assert delay_start_entity(_appliance(start_in, finish_in)) is start_in
    assert delay_start_entity(_appliance(finish_in)) is finish_in
    assert delay_start_entity(_appliance()) is None


def test_generate_delay_start() -> None:
    """The select is only offered on appliances with StartIn or FinishIn."""
    assert generate_delay_start(_appliance()) is None
    description = generate_delay_start(_appliance(_option(FINISH_IN_RELATIVE, 551)))
    assert description is not None
    assert description.entity == FINISH_IN_RELATIVE
    assert description.options == DELAY_START_OPTIONS


def test_apply_delay_start_without_delay_keeps_options() -> None:
    """No delay leaves the start options untouched."""
    appliance = _appliance(_option(FINISH_IN_RELATIVE, 551, 5100))
    assert apply_delay_start(appliance, DelayStart(), {1: 2}) == {1: 2}


def test_apply_delay_start_start_in() -> None:
    """StartInRelative gets the delay itself."""
    appliance = _appliance(_option(START_IN_RELATIVE, 550))
    delay_start = DelayStart(option="2h")
    assert apply_delay_start(appliance, delay_start, {1: 2}) == {1: 2, 550: 7200}


def test_apply_delay_start_finish_in_from_options() -> None:
    """
    FinishInRelative gets the program duration plus the delay.

    With a program selected, the appliance reports FinishInRelative as the
    program's own duration (Siemens WM16XKH2EU washer, #146).
    """
    appliance = _appliance(_option(FINISH_IN_RELATIVE, 551, 9999))
    delay_start = DelayStart(option="1h")
    assert apply_delay_start(appliance, delay_start, {551: 5100}) == {551: 8700}


def test_apply_delay_start_finish_in_from_entity_value() -> None:
    """Without FinishInRelative in the start options, its reported value is the base."""
    appliance = _appliance(_option(FINISH_IN_RELATIVE, 551, 5100))
    delay_start = DelayStart(option="1h")
    assert apply_delay_start(appliance, delay_start, {}) == {551: 8700}


def test_apply_delay_start_finish_in_duration_unknown() -> None:
    """Without a known duration the delay can't be applied."""
    appliance = _appliance(_option(FINISH_IN_RELATIVE, 551, None))
    with pytest.raises(HomeAssistantError) as err:
        apply_delay_start(appliance, DelayStart(option="1h"), {})
    assert err.value.translation_key == "delay_start_duration_unknown"


def test_apply_delay_start_too_long() -> None:
    """A delay past the appliance's maximum is refused with a clear error."""
    appliance = _appliance(_option(FINISH_IN_RELATIVE, 551, 5100, max_value=86400))
    with pytest.raises(HomeAssistantError) as err:
        apply_delay_start(appliance, DelayStart(option="24h"), {})
    assert err.value.translation_key == "delay_start_too_long"
    assert err.value.translation_placeholders == {"max_hours": "24"}


async def test_select_defaults_to_no_delay_and_stores_choice(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """The select starts at No delay and keeps the picked delay in HA only."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    state = hass.states.get(SELECT_ENTITY_ID)
    assert state
    assert state.state == DELAY_START_NONE
    assert state.attributes["options"] == DELAY_START_OPTIONS

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: SELECT_ENTITY_ID, ATTR_OPTION: "2h"},
        blocking=True,
    )
    assert hass.states.get(SELECT_ENTITY_ID).state == "2h"
    # Nothing is written to the appliance until Start is pressed.
    mock_appliance.session.send_sync.assert_not_awaited()


async def test_select_restores_last_choice(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """A delay picked before a restart is still there afterwards."""
    mock_restore_cache(hass, (State(SELECT_ENTITY_ID, "3h"),))
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    assert hass.states.get(SELECT_ENTITY_ID).state == "3h"


async def test_start_applies_delay_and_resets_it(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """
    Start sends FinishInRelative = program duration + delay, then resets the select.

    The washer reports FinishInRelative as the program's duration once a
    program is selected (5100 s here); +2 h makes it 12300 s.
    """
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.SelectedProgram"].update({"value": 500})
    await mock_appliance.entities["BSH.Common.Option.FinishInRelative"].update({"value": 5100})
    await hass.async_block_till_done()

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: SELECT_ENTITY_ID, ATTR_OPTION: "2h"},
        blocking=True,
    )
    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: START_ENTITY_ID}, blocking=True
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data={"program": 500, "options": [{"uid": 405, "value": 12300}]},
        )
    )
    assert hass.states.get(SELECT_ENTITY_ID).state == DELAY_START_NONE


async def test_start_refuses_too_long_delay_and_keeps_it(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """A delay past the maximum is refused without starting, and stays selected."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.SelectedProgram"].update({"value": 500})
    await mock_appliance.entities["BSH.Common.Option.FinishInRelative"].update({"value": 5100})
    await hass.async_block_till_done()

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: SELECT_ENTITY_ID, ATTR_OPTION: "24h"},
        blocking=True,
    )
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: START_ENTITY_ID}, blocking=True
        )

    mock_appliance.session.send_sync.assert_not_awaited()
    assert hass.states.get(SELECT_ENTITY_ID).state == "24h"


def test_apply_delay_start_finish_in_prefers_estimated_total_program_time() -> None:
    """
    The base is the program duration, not a finish time already set by hand.

    If someone set FinishInRelative to 2 h through the number (on an appliance
    that accepts that write), +1 h must give program duration + 1 h, not 3 h.
    """
    appliance = _appliance(
        _option(FINISH_IN_RELATIVE, 551, 7200),
        _option(ESTIMATED_TOTAL_PROGRAM_TIME, 552, 3600),
    )
    delay_start = DelayStart(option="1h")
    assert apply_delay_start(appliance, delay_start, {551: 7200}) == {551: 7200}


def test_apply_delay_start_skips_unavailable_estimated_total_program_time() -> None:
    """An unavailable EstimatedTotalProgramTime falls back to FinishInRelative."""
    estimated = _option(ESTIMATED_TOTAL_PROGRAM_TIME, 552, 9999)
    estimated.available = False
    appliance = _appliance(_option(FINISH_IN_RELATIVE, 551, 5100), estimated)
    delay_start = DelayStart(option="1h")
    assert apply_delay_start(appliance, delay_start, {}) == {551: 8700}
