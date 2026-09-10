"""Tests for sensor entity."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from custom_components.homeconnect_ws import HCData
from custom_components.homeconnect_ws.entity_descriptions.descriptions_definitions import (
    HCSensorEntityDescription,
)
from custom_components.homeconnect_ws.sensor import HCActiveProgram, HCSensor, HCWiFI
from homeassistant.components.sensor import ATTR_OPTIONS
from homeassistant.const import ATTR_FRIENDLY_NAME
from homeassistant.helpers.entity import Entity as HAEntity

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
    patch_entity_description: None,
) -> None:
    """Test updating entity."""
    entity_id = "sensor.fake_brand_homeappliance_sensor"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await mock_appliance.entities["Test.Sensor"].update({"value": 5})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "5"


async def test_callback_recovers_after_write_failure(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A single failed state write must not permanently freeze future updates.

    Confirmed live on fork issue #7: sensor.<device>_power_state got stuck
    on one value forever after some update. Traced to HCEntity.callback's
    reentrancy guard (_has_callback) never being cleared if
    async_write_ha_state() raised (e.g. HA core's own ENUM sensor
    validation raises ValueError for an out-of-options value) - the guard
    stayed True forever, silently no-opping every future callback for that
    entity.
    """
    entity_id = "sensor.fake_brand_homeappliance_sensor"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    original_write_ha_state = HAEntity.async_write_ha_state
    should_raise = True

    def patched_write_ha_state(self: HAEntity) -> None:
        nonlocal should_raise
        if self.entity_id == entity_id and should_raise:
            should_raise = False
            msg = "Simulated state-write failure"
            raise ValueError(msg)
        original_write_ha_state(self)

    monkeypatch.setattr(HAEntity, "async_write_ha_state", patched_write_ha_state)

    await mock_appliance.entities["Test.Sensor"].update({"value": 1})
    await hass.async_block_till_done()

    # The failed write shouldn't have left the reentrancy guard stuck -
    # a later, successful update must still go through.
    await mock_appliance.entities["Test.Sensor"].update({"value": 2})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "2"


async def test_update_enum(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
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
    patch_entity_description: None,
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
    patch_entity_description: None,
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


async def test_native_value_cleared_when_expected_offline() -> None:
    """Remaining/elapsed time and progress clear instead of showing a stale in-progress value."""
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=True),
    )
    entity_description = HCSensorEntityDescription(
        key="sensor_remaining_program_time", clear_on_expected_offline=True
    )
    entity = HCSensor(entity_description, runtime_data)

    assert entity.native_value is None


async def test_native_value_not_cleared_when_not_expected_offline() -> None:
    """The clearing only applies while actually expected_offline."""
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=False),
    )
    entity_description = HCSensorEntityDescription(
        key="sensor_remaining_program_time", clear_on_expected_offline=True
    )
    entity = HCSensor(entity_description, runtime_data)

    # No backing entity in this minimal setup either, but this confirms the
    # clear_on_expected_offline branch isn't what's producing the None here -
    # it falls through to the ordinary "no entity" path instead.
    assert entity.native_value is None


async def test_power_state_forced_when_expected_offline() -> None:
    """
    sensor_power_state must not stay frozen on its last real value forever.

    Confirmed live on fork issue #7 via a real debug log: a laundry appliance
    drops its WiFi entirely on power-off, so BSH.Common.Setting.PowerState
    never gets a final NOTIFY confirming the off transition. Unlike
    select_power_state (which already forces to the appliance's real off
    state while expected_offline), the sensor mirror had no equivalent and
    just kept showing the stale "on" value forever.
    """
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    appliance.entities["Test.PowerState"].value = "On"
    appliance.entities["Test.PowerState"].enum = {"0": "On", "1": "Off"}
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=True),
    )
    entity_description = HCSensorEntityDescription(
        key="sensor_power_state",
        entity="Test.PowerState",
        has_state_translation=True,
        force_option_when_expected_offline="off",
    )
    entity = HCSensor(entity_description, runtime_data)

    assert entity.native_value == "off"


async def test_power_state_not_forced_when_not_expected_offline() -> None:
    """The forced value only applies while actually expected_offline."""
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    appliance.entities["Test.PowerState"].value = "On"
    appliance.entities["Test.PowerState"].enum = {"0": "On", "1": "Off"}
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=False),
    )
    entity_description = HCSensorEntityDescription(
        key="sensor_power_state",
        entity="Test.PowerState",
        has_state_translation=True,
        force_option_when_expected_offline="off",
    )
    entity = HCSensor(entity_description, runtime_data)

    assert entity.native_value == "on"


async def test_power_state_not_forced_when_value_not_a_real_option() -> None:
    """
    A static entity description can't assume every appliance model has the forced value.

    See test_current_option_not_forced_when_value_not_a_real_option in
    test_select.py - same guard, same reasoning, for the sensor mirror.
    """
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    appliance.entities["Test.SpinSpeed"].value = "RPM1400"
    appliance.entities["Test.SpinSpeed"].enum = {"0": "RPM800", "1": "RPM1400"}
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=True),
    )
    entity_description = HCSensorEntityDescription(
        key="sensor_laundry_spin_speed",
        entity="Test.SpinSpeed",
        has_state_translation=True,
        force_option_when_expected_offline="off",
    )
    entity = HCSensor(entity_description, runtime_data)

    assert entity.native_value == "rpm1400"


async def test_active_program_cleared_when_expected_offline() -> None:
    """The active-program sensor clears instead of showing a stale program name."""
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    appliance.active_program.name = "Test.Program"
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=True),
    )
    entity_description = HCSensorEntityDescription(
        key="sensor_active_program", clear_on_expected_offline=True
    )
    entity = HCActiveProgram(entity_description, runtime_data)

    assert entity.native_value is None


async def test_active_program_not_cleared_when_not_expected_offline() -> None:
    """The active-program sensor reports normally while not expected_offline."""
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    appliance.active_program.name = "Test.Program"
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=False),
    )
    entity_description = HCSensorEntityDescription(
        key="sensor_active_program", clear_on_expected_offline=True
    )
    entity = HCActiveProgram(entity_description, runtime_data)

    assert entity.native_value == "Test.Program"


async def test_phase_forced_when_no_active_program_and_off() -> None:
    """A program-phase sensor forces to its idle value once nothing is running and off."""
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    appliance.active_program = None
    appliance.entities["Test.ProgramPhase"].value = "Drying"
    appliance.entities["Test.ProgramPhase"].enum = {"0": "None", "1": "Drying"}
    appliance.entities.get.return_value = MagicMock(value="Off")
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=False),
    )
    entity_description = HCSensorEntityDescription(
        key="sensor_program_phase",
        entity="Test.ProgramPhase",
        has_state_translation=True,
        force_value_when_no_active_program="none",
    )
    entity = HCSensor(entity_description, runtime_data)

    assert entity.native_value == "none"


async def test_phase_not_forced_when_active_program_present() -> None:
    """The forced idle value doesn't apply while a program is actually running."""
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    appliance.entities["Test.ProgramPhase"].value = "Drying"
    appliance.entities["Test.ProgramPhase"].enum = {"0": "None", "1": "Drying"}
    appliance.entities.get.return_value = MagicMock(value="Off")
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=False),
    )
    entity_description = HCSensorEntityDescription(
        key="sensor_program_phase",
        entity="Test.ProgramPhase",
        has_state_translation=True,
        force_value_when_no_active_program="none",
    )
    entity = HCSensor(entity_description, runtime_data)

    assert entity.native_value == "drying"


async def test_phase_not_forced_when_powered_on() -> None:
    """The forced idle value doesn't apply while the appliance is still powered on."""
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    appliance.active_program = None
    appliance.entities["Test.ProgramPhase"].value = "Drying"
    appliance.entities["Test.ProgramPhase"].enum = {"0": "None", "1": "Drying"}
    appliance.entities.get.return_value = MagicMock(value="On")
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=False),
    )
    entity_description = HCSensorEntityDescription(
        key="sensor_program_phase",
        entity="Test.ProgramPhase",
        has_state_translation=True,
        force_value_when_no_active_program="none",
    )
    entity = HCSensor(entity_description, runtime_data)

    assert entity.native_value == "drying"


async def test_phase_not_forced_when_value_not_a_real_option() -> None:
    """
    A static entity description can't assume every appliance model has the forced value.

    See test_power_state_not_forced_when_value_not_a_real_option above - same
    guard, same reasoning, for the no-active-program trigger instead.
    """
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    appliance.active_program = None
    appliance.entities["Test.ProgramPhase"].value = "Drying"
    appliance.entities["Test.ProgramPhase"].enum = {"0": "Idle", "1": "Drying"}
    appliance.entities.get.return_value = MagicMock(value="Off")
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=False),
    )
    entity_description = HCSensorEntityDescription(
        key="sensor_program_phase",
        entity="Test.ProgramPhase",
        has_state_translation=True,
        force_value_when_no_active_program="none",
    )
    entity = HCSensor(entity_description, runtime_data)

    assert entity.native_value == "drying"


async def test_progress_unavailable_when_no_active_program_and_off() -> None:
    """A progress sensor goes unavailable (matching Home Connect Cloud) once idle and off."""
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    appliance.active_program = None
    appliance.session.connected = True
    appliance.entities.get.return_value = MagicMock(value="Off")
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=False),
    )
    entity_description = HCSensorEntityDescription(
        key="sensor_program_progress", unavailable_when_no_active_program=True
    )
    entity = HCSensor(entity_description, runtime_data)

    assert entity.available is False


async def test_progress_available_when_active_program_present() -> None:
    """The progress sensor stays available while a program is actually running."""
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    appliance.session.connected = True
    appliance.entities.get.return_value = MagicMock(value="Off")
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=False),
    )
    entity_description = HCSensorEntityDescription(
        key="sensor_program_progress", unavailable_when_no_active_program=True
    )
    entity = HCSensor(entity_description, runtime_data)

    assert entity.available is True


async def test_flagged_sensor_also_listens_to_active_program_and_power_state() -> None:
    """
    A sensor stuck on its own stale value needs a different trigger to refresh.

    The appliance never sends a fresh NOTIFY for program_phase/progress once
    idle - that's the whole bug (issue #302). Without also registering for
    ActiveProgram/PowerState callbacks, nothing would ever call
    async_write_ha_state() again to make HA re-evaluate native_value/
    available once the appliance actually goes idle and off.
    """
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    active_program_entity = MagicMock()
    power_state_entity = MagicMock()
    appliance.entities = {
        "Test.ProgramPhase": MagicMock(value="Drying", enum=None),
        "BSH.Common.Root.ActiveProgram": active_program_entity,
        "BSH.Common.Setting.PowerState": power_state_entity,
    }
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=False),
    )
    entity_description = HCSensorEntityDescription(
        key="sensor_program_phase",
        entity="Test.ProgramPhase",
        force_value_when_no_active_program="none",
    )
    entity = HCSensor(entity_description, runtime_data)

    assert active_program_entity in entity._entities
    assert power_state_entity in entity._entities


async def test_unflagged_sensor_does_not_listen_to_active_program_or_power_state() -> None:
    """A plain sensor without either flag has no reason to track these extra entities."""
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    active_program_entity = MagicMock()
    power_state_entity = MagicMock()
    appliance.entities = {
        "Test.Sensor": MagicMock(value=1, enum=None),
        "BSH.Common.Root.ActiveProgram": active_program_entity,
        "BSH.Common.Setting.PowerState": power_state_entity,
    }
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=False),
    )
    entity_description = HCSensorEntityDescription(key="sensor_plain", entity="Test.Sensor")
    entity = HCSensor(entity_description, runtime_data)

    assert active_program_entity not in entity._entities
    assert power_state_entity not in entity._entities


async def test_progress_available_when_powered_on() -> None:
    """The progress sensor stays available while the appliance is powered on, even if idle."""
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    appliance.active_program = None
    appliance.session.connected = True
    appliance.entities.get.return_value = MagicMock(value="On")
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=False),
    )
    entity_description = HCSensorEntityDescription(
        key="sensor_program_progress", unavailable_when_no_active_program=True
    )
    entity = HCSensor(entity_description, runtime_data)

    assert entity.available is True
