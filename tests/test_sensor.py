"""Tests for sensor entity."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from custom_components.homeconnect_ws import HCData
from custom_components.homeconnect_ws.entity_descriptions.descriptions_definitions import (
    HCSensorEntityDescription,
)
from custom_components.homeconnect_ws.sensor import (
    HCSensor,
)
from homeassistant.components.sensor import ATTR_OPTIONS
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_FRIENDLY_NAME, STATE_UNAVAILABLE, STATE_UNKNOWN, Platform
from homeassistant.helpers.entity import Entity as HAEntity
from pytest_homeassistant_custom_component.common import snapshot_platform

from . import (
    answer_network_info,
    drop_connection,
    setup_config_entry,
    setup_integration,
    update_entity,
)
from .const import DISHWASHER_DESCRIPTION, MOCK_CONFIG_DATA

if TYPE_CHECKING:
    from home_disconnect import Appliance
    from home_disconnect.messages import Message
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from syrupy.assertion import SnapshotAssertion


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "mock_dishwasher")
async def test_sensors(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test the sensor entities of a dishwasher in the middle of a program."""
    with patch("custom_components.homeconnect_ws.PLATFORMS", [Platform.SENSOR]):
        await setup_integration(hass, mock_config_entry)

    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


async def test_setup(
    hass: HomeAssistant,
    mock_appliance: Appliance,
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
        "test_program_fan1",
        "test_program_fan2",
    ]


async def test_update(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_entity_description: None,
) -> None:
    """Test updating entity."""
    entity_id = "sensor.fake_brand_homeappliance_sensor"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await update_entity(mock_appliance.entities["Test.Sensor"], {"value": 5})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "5"


async def test_update_value_fn(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_entity_description: None,
) -> None:
    """Test that value_fn converts the appliance's value."""
    entity_id = "sensor.fake_brand_homeappliance_sensor_scaled"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await update_entity(mock_appliance.entities["Test.Sensor"], {"value": 2500})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "2.5"


async def test_callback_recovers_after_write_failure(
    hass: HomeAssistant,
    mock_appliance: Appliance,
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

    await update_entity(mock_appliance.entities["Test.Sensor"], {"value": 1})
    await hass.async_block_till_done()

    # The failed write shouldn't have left the reentrancy guard stuck -
    # a later, successful update must still go through.
    await update_entity(mock_appliance.entities["Test.Sensor"], {"value": 2})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "2"


async def test_update_enum(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_entity_description: None,
) -> None:
    """Test updating entity with enum."""
    entity_id = "sensor.fake_brand_homeappliance_sensor_enum"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await update_entity(mock_appliance.entities["Test.Sensor.Enum"], {"value": 0})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "Off"

    await update_entity(mock_appliance.entities["Test.Sensor.Enum"], {"value": 1})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "On"


async def test_update_event(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_entity_description: None,
) -> None:
    """Test updating event sensor."""
    entity_id = "sensor.fake_brand_homeappliance_sensor_event"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await update_entity(mock_appliance.entities["Test.Event1"], {"value": 0})
    await update_entity(mock_appliance.entities["Test.Event2"], {"value": 0})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "No Event"

    await update_entity(mock_appliance.entities["Test.Event1"], {"value": 1})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "Event1"

    await update_entity(mock_appliance.entities["Test.Event2"], {"value": 1})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "Event2"

    await update_entity(mock_appliance.entities["Test.Event2"], {"value": 0})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "Event1"


async def test_update_active_program(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_entity_description: None,
) -> None:
    """Test updating active program entity."""
    entity_id = "sensor.fake_brand_homeappliance_activeprogram"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await update_entity(mock_appliance.entities["Test.ActiveProgram"], {"value": 500})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "test_program_program1"

    await update_entity(mock_appliance.entities["Test.ActiveProgram"], {"value": 502})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "Named Favorite"


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_network_sensors(
    hass: HomeAssistant,
    mock_dishwasher: Appliance,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The WiFi and IP address sensors show what the appliance answers on /ni/info."""
    answer_network_info(
        mock_dishwasher,
        [
            {
                "interfaceID": 0,
                "type": "WiFi",
                "rssi": -58,
                "ipV4": {
                    "ipAddress": "192.168.1.50",
                    "prefixSize": 24,
                    "gateway": "192.168.1.1",
                    "dnsServer": "192.168.1.1",
                },
            }
        ],
    )
    await setup_integration(hass, mock_config_entry)

    assert hass.states.get("sensor.fake_brand_dishwasher_wifi_signal_strength").state == "-58"
    ipv4 = hass.states.get("sensor.fake_brand_dishwasher_ipv4_address")
    assert ipv4.state == "192.168.1.50"
    assert ipv4.attributes["prefix_size"] == 24
    assert ipv4.attributes["gateway"] == "192.168.1.1"
    assert ipv4.attributes["dns_server"] == "192.168.1.1"
    # An appliance with no IPv6 address just has no value, not an error
    ipv6 = hass.states.get("sensor.fake_brand_dishwasher_ipv6_address")
    assert ipv6.state == STATE_UNKNOWN
    assert "gateway" not in ipv6.attributes


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_network_sensors_without_network_service(
    hass: HomeAssistant,
    mock_dishwasher: Appliance,
    mock_config_entry: MockConfigEntry,
) -> None:
    """An appliance without the /ni service gets network sensors without a value."""
    del mock_dishwasher.session.service_versions["ni"]
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    for name in ("wifi_signal_strength", "ipv4_address", "ipv6_address"):
        assert hass.states.get(f"sensor.fake_brand_dishwasher_{name}").state == STATE_UNKNOWN


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_network_info_does_not_block_setup(
    hass: HomeAssistant,
    mock_dishwasher: Appliance,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A slow /ni/info answer doesn't hold up setup; the sensors fill in once it comes."""
    answered = asyncio.Event()
    respond = mock_dishwasher.session.request.side_effect

    async def _slow_network_info(message: Message) -> Message:
        if message.resource == "/ni/info":
            await answered.wait()
            return message.response([{"interfaceID": 0, "type": "WiFi", "rssi": -58}])
        return await respond(message)

    mock_dishwasher.session.request.side_effect = _slow_network_info
    mock_config_entry.add_to_hass(hass)
    # Not async_block_till_done(): that would wait for the unanswered request too
    async with asyncio.timeout(5):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    entity_id = "sensor.fake_brand_dishwasher_wifi_signal_strength"
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    answered.set()
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == "-58"


@pytest.mark.parametrize(
    ("close_code", "expected"),
    [
        # Turned off: the washer closes the connection and turns its WiFi off
        (1000, STATE_UNKNOWN),
        # A dropped connection is a fault, not the washer turning off
        (1006, STATE_UNAVAILABLE),
    ],
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_program_sensors_when_washer_disconnects(
    hass: HomeAssistant,
    mock_washer: Appliance,
    washer_config_entry: MockConfigEntry,
    close_code: int,
    expected: str,
) -> None:
    """
    A washer that turns off clears its program sensors instead of freezing them mid-program.

    Laundry appliances turn their WiFi off with the appliance, so the last
    values (e.g. 30 minutes left) never get updated (fork issue #7).
    """
    await setup_integration(hass, washer_config_entry)
    assert hass.states.get("sensor.fake_brand_washer_remaining_program_time").state == "0.5"
    assert hass.states.get("sensor.fake_brand_washer_active_program").state == (
        "laundrycare_washer_program_cotton"
    )

    await drop_connection(mock_washer, close_code)
    await hass.async_block_till_done()

    for name in ("remaining_program_time", "active_program"):
        assert hass.states.get(f"sensor.fake_brand_washer_{name}").state == expected


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


@pytest.mark.parametrize(
    ("active_program", "power_state", "phase", "progress"),
    [
        # Nothing running and off: the phase and progress the appliance stopped updating
        (None, 1, "none", STATE_UNAVAILABLE),
        (8193, 1, "mainwash", "40"),
        (None, 2, "mainwash", "40"),
    ],
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_phase_and_progress_when_idle_and_off(
    hass: HomeAssistant,
    mock_dishwasher: Appliance,
    mock_config_entry: MockConfigEntry,
    active_program: int | None,
    power_state: int,
    phase: str,
    progress: str,
) -> None:
    """
    Once nothing runs and the dishwasher is off, phase shows none and progress goes unavailable.

    The appliance stops updating them once idle (issue #302), so they follow
    ActiveProgram and PowerState instead; progress matches Home Connect Cloud.
    """
    await setup_integration(hass, mock_config_entry)

    await update_entity(mock_dishwasher.entities.active_program, {"value": active_program})
    await update_entity(
        mock_dishwasher.entities["BSH.Common.Setting.PowerState"], {"value": power_state}
    )
    await hass.async_block_till_done()

    assert hass.states.get("sensor.fake_brand_dishwasher_program_phase").state == phase
    assert hass.states.get("sensor.fake_brand_dishwasher_program_progress").state == progress


_PHASE_WITHOUT_NONE = deepcopy(DISHWASHER_DESCRIPTION)
_PHASE_WITHOUT_NONE["status"][1]["enumeration"] = {"0": "Idle", "2": "MainWash"}


@pytest.mark.parametrize("dishwasher_description", [_PHASE_WITHOUT_NONE], indirect=True)
async def test_phase_not_forced_to_value_appliance_lacks(
    hass: HomeAssistant,
    mock_dishwasher: Appliance,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    A phase stays as it is when the appliance has no "None" phase to show.

    Showing a value outside the sensor's options makes Home Assistant reject it.
    """
    await setup_integration(hass, mock_config_entry)

    await update_entity(mock_dishwasher.entities.active_program, {"value": None})
    await update_entity(mock_dishwasher.entities["BSH.Common.Setting.PowerState"], {"value": 1})
    await hass.async_block_till_done()

    assert hass.states.get("sensor.fake_brand_dishwasher_program_phase").state == "mainwash"
    assert "not in the list of options" not in caplog.text


async def test_elapsed_time_shown_while_program_runs(
    hass: HomeAssistant,
    mock_washer: Appliance,
    washer_config_entry: MockConfigEntry,
) -> None:
    """
    Elapsed time shows while a program runs, even though the appliance flags it unavailable.

    A Thermador PRG486WDH oven running top/bottom heating with no timer set
    reports BSH.Common.Option.ElapsedProgramTime as available=false while its
    value keeps counting up (2557s in the reporting diagnostics).
    """
    entity_id = "sensor.fake_brand_washer_elapsed_program_time"
    elapsed = mock_washer.entities["BSH.Common.Option.ElapsedProgramTime"]
    await update_entity(elapsed, {"available": False})
    await setup_integration(hass, washer_config_entry)
    assert hass.states.get(entity_id).state != STATE_UNAVAILABLE

    # With nothing running, the appliance's own flag applies
    await update_entity(mock_washer.entities.active_program, {"value": None})
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    # ... until a program starts again, without the elapsed time itself changing
    await update_entity(mock_washer.entities.active_program, {"value": 32768})
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state != STATE_UNAVAILABLE

    # An active program alone isn't enough: there has to be a value to show
    await update_entity(elapsed, {"value": None})
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    # It never overrides a lost connection
    await update_entity(elapsed, {"value": 2557})
    await drop_connection(mock_washer, 1006)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE


async def test_progress_shown_with_remaining_time(
    hass: HomeAssistant,
    mock_washer: Appliance,
    washer_config_entry: MockConfigEntry,
) -> None:
    """
    Progress shows while a program with a remaining time runs, even though it's flagged unavailable.

    A Bosch WTX87E40 dryer reports ProgramProgress as available=false, access=none while its
    value keeps going up (fork issue #206).
    """
    entity_id = "sensor.fake_brand_washer_program_progress"
    remaining = mock_washer.entities["BSH.Common.Option.RemainingProgramTime"]
    await update_entity(
        mock_washer.entities["BSH.Common.Option.ProgramProgress"],
        {"available": False, "access": "none"},
    )
    await setup_integration(hass, washer_config_entry)
    assert hass.states.get(entity_id).state == "84"

    # Without a remaining time (an oven with no timer set), the appliance's flag applies,
    # and it follows the remaining time coming and going
    await update_entity(remaining, {"value": None})
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    await update_entity(remaining, {"value": 1800})
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "84"

    # The same when the remaining time is flagged unavailable
    await update_entity(remaining, {"available": False})
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE
    await update_entity(remaining, {"available": True})

    # ... or nothing runs
    await update_entity(mock_washer.entities.active_program, {"value": None})
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE
