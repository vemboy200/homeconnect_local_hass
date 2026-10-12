"""Tests for the "Delay start" select and how the Start button passes it on."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from custom_components.homeconnect_ws.entity_descriptions.common import generate_delay_start
from custom_components.homeconnect_ws.helpers import (
    DELAY_START_NONE,
    DELAY_START_OPTIONS,
    FINISH_IN_RELATIVE,
    START_IN_RELATIVE,
    DelayStart,
    delay_start_entity,
)
from home_disconnect.messages import Action, Message
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.components.select import ATTR_OPTION, SERVICE_SELECT_OPTION
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import mock_restore_cache

from . import setup_config_entry, update_entity
from .const import MOCK_CONFIG_DATA

if TYPE_CHECKING:
    from home_disconnect import Appliance
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


async def test_select_defaults_to_no_delay_and_stores_choice(
    hass: HomeAssistant,
    mock_appliance: Appliance,
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
    mock_appliance.session.request.assert_not_awaited()


async def test_select_restores_last_choice(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_entity_description: None,
) -> None:
    """A delay picked before a restart is still there afterwards."""
    mock_restore_cache(hass, (State(SELECT_ENTITY_ID, "3h"),))
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    assert hass.states.get(SELECT_ENTITY_ID).state == "3h"


async def test_start_applies_delay_and_resets_it(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_entity_description: None,
) -> None:
    """
    Start sends FinishInRelative = program duration + delay, then resets the select.

    The washer reports FinishInRelative as the program's duration once a
    program is selected (5100 s here); +2 h makes it 12300 s.
    """
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await update_entity(mock_appliance.entities["Test.SelectedProgram"], {"value": 500})
    await update_entity(
        mock_appliance.entities["BSH.Common.Option.FinishInRelative"], {"value": 5100}
    )
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

    mock_appliance.session.request.assert_awaited_once_with(
        Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data=[{"program": 500, "options": [{"uid": 405, "value": 12300}]}],
        )
    )
    assert hass.states.get(SELECT_ENTITY_ID).state == DELAY_START_NONE


async def test_start_refuses_too_long_delay_and_keeps_it(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_entity_description: None,
) -> None:
    """A delay past the maximum is refused without starting, and stays selected."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await update_entity(mock_appliance.entities["Test.SelectedProgram"], {"value": 500})
    await update_entity(
        mock_appliance.entities["BSH.Common.Option.FinishInRelative"], {"value": 5100}
    )
    await hass.async_block_till_done()

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: SELECT_ENTITY_ID, ATTR_OPTION: "24h"},
        blocking=True,
    )
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: START_ENTITY_ID}, blocking=True
        )

    assert err.value.translation_key == "delay_start_too_long"
    assert err.value.translation_placeholders == {"max_hours": "24"}
    mock_appliance.session.request.assert_not_awaited()
    assert hass.states.get(SELECT_ENTITY_ID).state == "24h"


async def test_start_refuses_delay_without_duration(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_entity_description: None,
) -> None:
    """A FinishInRelative delay needs the program's duration; without it nothing starts."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await update_entity(mock_appliance.entities["Test.SelectedProgram"], {"value": 500})
    await hass.async_block_till_done()

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: SELECT_ENTITY_ID, ATTR_OPTION: "1h"},
        blocking=True,
    )
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: START_ENTITY_ID}, blocking=True
        )

    assert err.value.translation_key == "delay_start_duration_unknown"
    mock_appliance.session.request.assert_not_awaited()
