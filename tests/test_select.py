"""Tests for select entity."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from custom_components.homeconnect_ws import HCData
from custom_components.homeconnect_ws.entity_descriptions.descriptions_definitions import (
    HCSelectEntityDescription,
)
from custom_components.homeconnect_ws.select import HCSelect
from home_disconnect.entities import Access, Execution, Program
from home_disconnect.message import Action, Message
from homeassistant.components.select import (
    ATTR_OPTION,
    ATTR_OPTIONS,
    SERVICE_SELECT_OPTION,
)
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, ATTR_FRIENDLY_NAME, STATE_UNKNOWN
from homeassistant.exceptions import ServiceValidationError

from . import setup_config_entry
from .const import MOCK_CONFIG_DATA

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

    state = hass.states.get("select.fake_brand_homeappliance_select")
    assert state
    assert state.name == "Fake_brand HomeAppliance Select"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Fake_brand HomeAppliance Select"
    assert state.attributes[ATTR_OPTIONS] == ["Option1", "Option2", "Option3"]

    state = hass.states.get("select.fake_brand_homeappliance_select_translated")
    assert state
    assert state.name == "Fake_brand HomeAppliance Select.Translated"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Fake_brand HomeAppliance Select.Translated"
    assert state.attributes[ATTR_OPTIONS] == ["option1", "option2", "option3"]

    state = hass.states.get("select.fake_brand_homeappliance_select_options")
    assert state
    assert state.name == "Fake_brand HomeAppliance Select.Options"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Fake_brand HomeAppliance Select.Options"
    assert state.attributes[ATTR_OPTIONS] == ["option2"]

    state = hass.states.get("select.fake_brand_homeappliance_selectedprogram")
    assert state
    assert state.name == "Fake_brand HomeAppliance SelectedProgram"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Fake_brand HomeAppliance SelectedProgram"
    assert state.attributes[ATTR_OPTIONS] == [
        "Named Favorite",
        "favorite_002",
        "test_program_program1",
        "test_program_program2",
        "test_program_program3",
    ]


async def test_update(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test updating entity."""
    entity_id = "select.fake_brand_homeappliance_select"
    entity_id_translated = "select.fake_brand_homeappliance_select_translated"
    entity_id_options = "select.fake_brand_homeappliance_select_options"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await mock_appliance.entities["Test.Select"].update({"value": 0})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "Option1"

    state = hass.states.get(entity_id_translated)
    assert state.state == "option1"

    state = hass.states.get(entity_id_options)
    assert state.state == STATE_UNKNOWN

    await mock_appliance.entities["Test.Select"].update({"value": 1})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "Option2"

    state = hass.states.get(entity_id_translated)
    assert state.state == "option2"

    state = hass.states.get(entity_id_options)
    assert state.state == "option2"


async def test_select(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test selecting an option."""
    entity_id = "select.fake_brand_homeappliance_select"
    entity_id_translated = "select.fake_brand_homeappliance_select_translated"
    entity_id_options = "select.fake_brand_homeappliance_select_options"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {
            ATTR_ENTITY_ID: entity_id,
            ATTR_OPTION: "Option3",
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data={"uid": 203, "value": 2},
        )
    )
    mock_appliance.session.send_sync.reset_mock()

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {
            ATTR_ENTITY_ID: entity_id_translated,
            ATTR_OPTION: "option3",
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data={"uid": 203, "value": 2},
        )
    )
    mock_appliance.session.send_sync.reset_mock()

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {
            ATTR_ENTITY_ID: entity_id_options,
            ATTR_OPTION: "option2",
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data={"uid": 203, "value": 1},
        )
    )


async def test_update_program(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test updating program select entity."""
    entity_id = "select.fake_brand_homeappliance_selectedprogram"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.SelectedProgram"].update({"value": 500})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "test_program_program1"

    await mock_appliance.entities["Test.SelectedProgram"].update({"value": 502})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "Named Favorite"


async def test_update_program_from_active_program(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """current_option falls back to ActiveProgram when SelectedProgram has none set."""
    entity_id = "select.fake_brand_homeappliance_selectedprogram"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await mock_appliance.entities["Test.ActiveProgram"].update({"value": 501})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "test_program_program2"


async def test_start_only_program_available_with_read_only_selected_program(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """
    The program select stays available on hoods with a read-only SelectedProgram.

    Some hoods only expose their programs as Execution.START_ONLY and never
    make SelectedProgram itself writable - it's started via ActiveProgram
    instead, so SelectedProgram's own read-only access shouldn't gate this
    entity's availability.
    """
    entity_id = "select.fake_brand_homeappliance_selectedprogram"
    await mock_appliance.entities["Test.SelectedProgram"].update({"access": Access.READ})
    for program in mock_appliance.programs.values():
        await program.update({"execution": Execution.START_ONLY})
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    state = hass.states.get(entity_id)
    assert state.state == STATE_UNKNOWN

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {
            ATTR_ENTITY_ID: entity_id,
            ATTR_OPTION: "test_program_program2",
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data={
                "program": 501,
                "options": [{"uid": 401, "value": None}, {"uid": 402, "value": None}],
            },
        )
    )


async def test_selected_program_available_and_readonly_when_read_locked(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """
    Test the program select stays available with its value while SelectedProgram is read-locked.

    Confirmed live on fork issue #59 via a Bosch WGB244A0BY's own debug log:
    SelectedProgram's access flips READ_WRITE -> READ the instant a delayed
    start is armed, and back once the wash actually starts running - the
    select should keep showing the chosen program through that whole window
    instead of going unavailable, matching the same treatment already given
    to a locked Option.
    """
    entity_id = "select.fake_brand_homeappliance_selectedprogram"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.SelectedProgram"].update(
        {"value": 500, "access": "readwrite"}
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "test_program_program1"
    assert state.attributes["readonly"] is False

    await mock_appliance.entities["Test.SelectedProgram"].update({"access": "read"})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "test_program_program1"
    assert state.attributes["readonly"] is True


async def test_select_program_raises_when_selected_program_read_locked(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test picking a program raises a clear error instead of a silent/opaque failure."""
    entity_id = "select.fake_brand_homeappliance_selectedprogram"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    await mock_appliance.entities["Test.SelectedProgram"].update({"value": 500, "access": "read"})
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            SELECT_DOMAIN,
            SERVICE_SELECT_OPTION,
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_OPTION: "test_program_program2",
            },
            blocking=True,
        )

    mock_appliance.session.send_sync.assert_not_awaited()


async def test_select_program(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Test selecting an program."""
    entity_id = "select.fake_brand_homeappliance_selectedprogram"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {
            ATTR_ENTITY_ID: entity_id,
            ATTR_OPTION: "test_program_program2",
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/selectedProgram",
            action=Action.POST,
            data={
                "program": 501,
                # override_options=True: no merged-in options, since a stale
                # shared option value can be out of range for the newly
                # selected program (confirmed live on fork issues #9/#21).
                "options": [],
            },
        )
    )

    mock_appliance.session.send_sync.reset_mock()

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {
            ATTR_ENTITY_ID: entity_id,
            ATTR_OPTION: "test_program_program3",
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data={
                "program": 502,
                "options": [{"uid": 401, "value": None}, {"uid": 402, "value": None}],
            },
        )
    )


async def test_start_only_program_sends_known_option_values(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """
    Starting a start-only program includes its options' already-known values.

    Confirmed live on fork issue #14: a hood's Venting program requires a
    real level to be sent - blanking out every option unconditionally (the
    prior behavior) made the appliance reject the start with a 400, even
    though the level's current value was already known.
    """
    entity_id = "select.fake_brand_homeappliance_selectedprogram"
    await mock_appliance.entities["Test.Option1"].update({"value": 1})
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {
            ATTR_ENTITY_ID: entity_id,
            ATTR_OPTION: "test_program_program3",
        },
        blocking=True,
    )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data={
                "program": 502,
                "options": [{"uid": 401, "value": 1}, {"uid": 402, "value": None}],
            },
        )
    )


async def test_full_option_set_program_sends_complete_options(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """
    An appliance advertising fullOptionSet gets program and options in one write.

    Confirmed live on a Bosch HNG6764B6 oven: it marks its SelectedProgram
    fullOptionSet, and rejects both a bare POST to /ro/selectedProgram and an
    option sent as null - every one of its programs failed to select with a
    400. Test.Option2 has no value anywhere, so it is left out of the write
    entirely rather than sent as null.
    """
    entity_id = "select.fake_brand_homeappliance_selectedprogram"
    await mock_appliance.entities["Test.Option1"].update({"value": 1})
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    with patch.object(Program, "full_option_set", new=True, create=True):
        await hass.services.async_call(
            SELECT_DOMAIN,
            SERVICE_SELECT_OPTION,
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_OPTION: "test_program_program2",
            },
            blocking=True,
        )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data={
                "program": 501,
                "options": [{"uid": 401, "value": 1}],
            },
        )
    )


async def test_full_option_set_select_only_program_stays_on_selected_program(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """A select-only program keeps /ro/selectedProgram, but carries its options."""
    entity_id = "select.fake_brand_homeappliance_selectedprogram"
    await mock_appliance.entities["Test.Option1"].update({"value": 1})
    await mock_appliance.programs["Test.Program.Program2"].update(
        {"execution": Execution.SELECT_ONLY}
    )
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    with patch.object(Program, "full_option_set", new=True, create=True):
        await hass.services.async_call(
            SELECT_DOMAIN,
            SERVICE_SELECT_OPTION,
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_OPTION: "test_program_program2",
            },
            blocking=True,
        )

    mock_appliance.session.send_sync.assert_awaited_once_with(
        Message(
            resource="/ro/selectedProgram",
            action=Action.POST,
            data={
                "program": 501,
                "options": [{"uid": 401, "value": 1}],
            },
        )
    )


async def test_current_option_forced_when_expected_offline() -> None:
    """A laundry appliance's power_state select shows the forced value, not its stale one."""
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=True),
    )
    entity_description = HCSelectEntityDescription(
        key="select_power_state",
        options=["on", "off", "standby"],
        force_option_when_expected_offline="off",
    )
    entity = HCSelect(entity_description, runtime_data)

    assert entity.current_option == "off"


async def test_current_option_not_forced_when_not_expected_offline() -> None:
    """The forced value only applies while actually expected_offline."""
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=False),
    )
    entity_description = HCSelectEntityDescription(
        key="select_power_state",
        options=["on", "off", "standby"],
        force_option_when_expected_offline="off",
    )
    entity = HCSelect(entity_description, runtime_data)

    assert entity.current_option is None


async def test_current_option_not_forced_when_value_not_a_real_option() -> None:
    """
    A static entity description can't assume every appliance model has the forced value.

    Confirmed live on fork issue #7 for the dynamically-generated PowerState
    case: forcing to a value that isn't actually one of this appliance's
    options makes SelectEntity.state silently degrade to "Unknown" instead
    of showing anything meaningful. Statically-declared descriptions (e.g.
    select_laundry_spin_speed's force_option_when_expected_offline="off")
    need the same guard, since not every model is guaranteed to have that
    exact option.
    """
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=True),
    )
    entity_description = HCSelectEntityDescription(
        key="select_laundry_spin_speed",
        options=["rpm800", "rpm1200", "rpm1400"],
        force_option_when_expected_offline="off",
    )
    entity = HCSelect(entity_description, runtime_data)

    assert entity.current_option is None


async def test_options_does_not_crash_when_enum_not_yet_populated() -> None:
    """
    Confirmed live on fork issue #17.

    HA's SelectEntity.options raises AttributeError (killing entity setup
    entirely) if it's never set. An Option entity's enum isn't guaranteed
    to be populated by the time entities are constructed, unlike a
    Setting, so options must be computed live and fall back to an empty
    list rather than relying on something set once at __init__.
    """
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    appliance.entities["Cooking.Common.Option.Hood.Boost"].enum = None
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=False),
    )
    entity_description = HCSelectEntityDescription(
        key="select_hood_boost",
        entity="Cooking.Common.Option.Hood.Boost",
        has_state_translation=True,
    )
    entity = HCSelect(entity_description, runtime_data)

    assert entity.options == []
    assert entity.current_option is None
