"""Tests for the availability of options the program does not use."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from custom_components import homeconnect_ws
from custom_components.homeconnect_ws import entity_descriptions
from custom_components.homeconnect_ws.entity_descriptions.descriptions_definitions import (
    HCSwitchEntityDescription,
)
from homeassistant.const import STATE_UNAVAILABLE

from . import setup_config_entry, update_entity
from .const import ENTITY_DESCRIPTIONS, MOCK_CONFIG_DATA

if TYPE_CHECKING:
    from home_disconnect import Appliance
    from homeassistant.core import HomeAssistant

# Test.Option1 (401) is an option of the test programs, Hood.Boost (406) of none of them
USED_OPTION = "switch.fake_brand_homeappliance_used_option"
UNUSED_OPTION = "switch.fake_brand_homeappliance_unused_option"


@pytest.fixture
def patch_option_switches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Add a switch for an option the programs use and one they don't."""
    descriptions = {
        **ENTITY_DESCRIPTIONS,
        "switch": [
            HCSwitchEntityDescription(
                key="Test.UsedOption", name="Used Option", entity="Test.Option1"
            ),
            HCSwitchEntityDescription(
                key="Test.UnusedOption",
                name="Unused Option",
                entity="Cooking.Common.Option.Hood.Boost",
            ),
        ],
    }
    monkeypatch.setattr(
        entity_descriptions, "get_available_entities", Mock(return_value=descriptions)
    )
    monkeypatch.setattr(homeconnect_ws, "get_available_entities", Mock(return_value=descriptions))


def _unavailable(hass: HomeAssistant, entity_id: str) -> bool:
    state = hass.states.get(entity_id)
    assert state
    return state.state == STATE_UNAVAILABLE


async def test_no_program(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_option_switches: None,
) -> None:
    """Without a selected or active program, options are available as before."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await update_entity(mock_appliance.entities["Test.SelectedProgram"], {"value": 0})
    await update_entity(mock_appliance.entities["Test.ActiveProgram"], {"value": 0})
    await hass.async_block_till_done()

    assert not _unavailable(hass, USED_OPTION)
    assert not _unavailable(hass, UNUSED_OPTION)


async def test_selected_program(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_option_switches: None,
) -> None:
    """An option the selected program doesn't use is unavailable."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await update_entity(mock_appliance.entities["Test.SelectedProgram"], {"value": 500})
    await hass.async_block_till_done()
    assert not _unavailable(hass, USED_OPTION)
    assert _unavailable(hass, UNUSED_OPTION)

    # Deselecting the program makes it available again
    await update_entity(mock_appliance.entities["Test.SelectedProgram"], {"value": 0})
    await hass.async_block_till_done()
    assert not _unavailable(hass, UNUSED_OPTION)


async def test_active_program(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_option_switches: None,
) -> None:
    """An option the active program doesn't use is unavailable."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await update_entity(mock_appliance.entities["Test.SelectedProgram"], {"value": 0})
    await update_entity(mock_appliance.entities["Test.ActiveProgram"], {"value": 501})
    await hass.async_block_till_done()

    assert not _unavailable(hass, USED_OPTION)
    assert _unavailable(hass, UNUSED_OPTION)


async def test_program_without_option_list(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_option_switches: None,
) -> None:
    """A program that lists no options (here a favorite) changes nothing."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await update_entity(mock_appliance.entities["Test.SelectedProgram"], {"value": 502})
    await hass.async_block_till_done()

    assert not _unavailable(hass, USED_OPTION)
    assert not _unavailable(hass, UNUSED_OPTION)


async def test_used_option_follows_the_appliance(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_option_switches: None,
) -> None:
    """An option the program uses still follows the availability the appliance reports."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await update_entity(mock_appliance.entities["Test.SelectedProgram"], {"value": 500})
    await update_entity(mock_appliance.entities["Test.Option1"], {"available": False})
    await hass.async_block_till_done()

    assert _unavailable(hass, USED_OPTION)
