"""Tests for the Last finished sensor."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock

from custom_components.homeconnect_ws import coordinator as coordinator_module
from custom_components.homeconnect_ws.const import DOMAIN, LAST_FINISHED_VALUES
from custom_components.homeconnect_ws.entity_descriptions import get_available_entities
from custom_components.homeconnect_ws.entity_descriptions.common import generate_last_finished
from home_disconnect import ConnectionState, DisconnectedError
from home_disconnect.entities import Access, DeviceDescription, EntityDescription
from home_disconnect.testutils import MockAppliance
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_DESCRIPTION, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import State
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import mock_restore_cache_with_extra_data

from . import setup_config_entry
from .const import DEVICE_DESCRIPTION, MOCK_APPLIANCE_INFO, MOCK_CONFIG_DATA

if TYPE_CHECKING:
    import pytest
    from custom_components.homeconnect_ws import HCConfigEntry
    from custom_components.homeconnect_ws.coordinator import HomeConnectCoordinator
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant

OPERATION_STATE = "BSH.Common.Status.OperationState"
PROGRAM_FINISHED = "BSH.Common.Event.ProgramFinished"

INACTIVE, READY, RUN, FINISHED = 0, 1, 2, 3
OFF, PRESENT, CONFIRMED = 0, 1, 2

T0 = datetime(2026, 10, 7, 12, 0, 0, tzinfo=UTC)

OPERATION_STATE_DESCRIPTION = EntityDescription(
    uid=900,
    name=OPERATION_STATE,
    enumeration={"0": "Inactive", "1": "Ready", "2": "Run", "3": "Finished"},
    available=True,
    access=Access.READ,
)
PROGRAM_FINISHED_DESCRIPTION = EntityDescription(
    uid=901,
    name=PROGRAM_FINISHED,
    enumeration={"0": "Off", "1": "Present", "2": "Confirmed"},
)


def _mock_appliance(
    monkeypatch: pytest.MonkeyPatch,
    *,
    operation_state: int | None = INACTIVE,
    program_finished: bool = True,
    appliance_type: str = "HomeAppliance",
    connected: bool = True,
) -> MockAppliance:
    """
    Make the coordinator use a MockAppliance with the finished signals.

    operation_state is the raw value OperationState starts with (None leaves the
    entity out entirely); the ProgramFinished event starts out Off.
    """
    status = []
    if operation_state is not None:
        status.append({**OPERATION_STATE_DESCRIPTION, "default": operation_state})
    appliance = MockAppliance(
        DeviceDescription(
            info={**MOCK_APPLIANCE_INFO, "type": appliance_type},
            status=status,
            event=[PROGRAM_FINISHED_DESCRIPTION] if program_finished else [],
        ),
        "host",
        "mock_app",
        "mock_app_id",
        None,
        None,
    )
    appliance.session.connected = connected
    monkeypatch.setattr(coordinator_module, "HomeAppliance", Mock(return_value=appliance))
    monkeypatch.setattr(coordinator_module.HomeConnectCoordinator, "connected", connected)
    monkeypatch.setattr(coordinator_module.HomeConnectCoordinator, "synced", connected)
    return appliance


def _entity_id(hass: HomeAssistant) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{MOCK_APPLIANCE_INFO['deviceID']}-sensor_last_finished"
    )
    assert entity_id
    return entity_id


async def _update(hass: HomeAssistant, appliance: MockAppliance, name: str, value: int) -> None:
    await appliance.entities[name].update({"value": value})
    await hass.async_block_till_done()


async def test_finished_operation_state_sets_timestamp(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Each time OperationState reaches Finished, the sensor takes that moment."""
    freezer.move_to(T0)
    appliance = _mock_appliance(monkeypatch)
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    entity_id = _entity_id(hass)

    state = hass.states.get(entity_id)
    assert state
    assert state.state == STATE_UNKNOWN
    assert state.attributes["device_class"] == SensorDeviceClass.TIMESTAMP

    # Running is not finished
    await _update(hass, appliance, OPERATION_STATE, RUN)
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    freezer.move_to(T0 + timedelta(hours=1))
    await _update(hass, appliance, OPERATION_STATE, FINISHED)
    first_finish = (T0 + timedelta(hours=1)).isoformat()
    assert hass.states.get(entity_id).state == first_finish

    # Further updates while it is still Finished are the same finish
    freezer.move_to(T0 + timedelta(hours=2))
    await _update(hass, appliance, OPERATION_STATE, FINISHED)
    assert hass.states.get(entity_id).state == first_finish

    # Going back to idle keeps the timestamp
    await _update(hass, appliance, OPERATION_STATE, READY)
    assert hass.states.get(entity_id).state == first_finish

    # The next program finishing is a new finish
    await _update(hass, appliance, OPERATION_STATE, RUN)
    freezer.move_to(T0 + timedelta(hours=3))
    await _update(hass, appliance, OPERATION_STATE, FINISHED)
    assert hass.states.get(entity_id).state == (T0 + timedelta(hours=3)).isoformat()


async def test_finished_event_sets_timestamp_without_operation_state(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    freezer: FrozenDateTimeFactory,
) -> None:
    """An appliance with only the ProgramFinished event works too."""
    freezer.move_to(T0)
    appliance = _mock_appliance(monkeypatch, operation_state=None)
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    entity_id = _entity_id(hass)
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    freezer.move_to(T0 + timedelta(minutes=5))
    await _update(hass, appliance, PROGRAM_FINISHED, PRESENT)
    first_finish = (T0 + timedelta(minutes=5)).isoformat()
    assert hass.states.get(entity_id).state == first_finish

    # Acknowledging the event is not another finish
    freezer.move_to(T0 + timedelta(minutes=6))
    await _update(hass, appliance, PROGRAM_FINISHED, CONFIRMED)
    assert hass.states.get(entity_id).state == first_finish

    await _update(hass, appliance, PROGRAM_FINISHED, OFF)
    assert hass.states.get(entity_id).state == first_finish

    freezer.move_to(T0 + timedelta(minutes=30))
    await _update(hass, appliance, PROGRAM_FINISHED, PRESENT)
    assert hass.states.get(entity_id).state == (T0 + timedelta(minutes=30)).isoformat()


async def test_both_signals_for_one_finish_count_once(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    freezer: FrozenDateTimeFactory,
) -> None:
    """An appliance reporting OperationState and the event for one finish isn't counted twice."""
    freezer.move_to(T0)
    appliance = _mock_appliance(monkeypatch)
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    entity_id = _entity_id(hass)
    await _update(hass, appliance, OPERATION_STATE, RUN)

    freezer.move_to(T0 + timedelta(minutes=1))
    await _update(hass, appliance, PROGRAM_FINISHED, PRESENT)
    first_finish = (T0 + timedelta(minutes=1)).isoformat()
    assert hass.states.get(entity_id).state == first_finish

    # Whichever signal comes second, minutes later, doesn't move it
    freezer.move_to(T0 + timedelta(minutes=2))
    await _update(hass, appliance, OPERATION_STATE, FINISHED)
    assert hass.states.get(entity_id).state == first_finish
    await _update(hass, appliance, PROGRAM_FINISHED, CONFIRMED)
    assert hass.states.get(entity_id).state == first_finish
    await _update(hass, appliance, PROGRAM_FINISHED, OFF)
    assert hass.states.get(entity_id).state == first_finish


async def test_state_at_startup_is_not_a_finish(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    freezer: FrozenDateTimeFactory,
) -> None:
    """An appliance that is already Finished when it is first seen has not just finished."""
    freezer.move_to(T0)
    appliance = _mock_appliance(monkeypatch, operation_state=FINISHED)
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    entity_id = _entity_id(hass)
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    await _update(hass, appliance, OPERATION_STATE, FINISHED)
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    await _update(hass, appliance, OPERATION_STATE, RUN)
    freezer.move_to(T0 + timedelta(hours=1))
    await _update(hass, appliance, OPERATION_STATE, FINISHED)
    assert hass.states.get(entity_id).state == (T0 + timedelta(hours=1)).isoformat()


async def _setup_washer(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> tuple[MockAppliance, HomeConnectCoordinator, str]:
    """
    Set up a washer that has just connected, the way the integration does it.

    appliance.connect() has returned and the coordinator reports it connected,
    but the library hasn't synced the appliance's state yet (see _sync).

    (No freezer in the tests using this: a frozen clock stalls the washer's
    background connect loop during setup.)
    """
    appliance = _mock_appliance(
        monkeypatch, appliance_type="Washer", operation_state=INACTIVE, connected=False
    )
    # The coordinator goes by the config entry's type: a washer is set up
    # without waiting for the connection
    washer_config = {
        **MOCK_CONFIG_DATA,
        CONF_DESCRIPTION: {
            **DEVICE_DESCRIPTION,
            "info": {**MOCK_APPLIANCE_INFO, "type": "Washer"},
        },
    }
    assert await setup_config_entry(hass, washer_config)
    entity_id = _entity_id(hass)
    entry: HCConfigEntry = hass.config_entries.async_entries(DOMAIN)[0]
    coordinator = entry.runtime_data.coordinator
    appliance._ext_connection_state_callback = coordinator._connection_state_callback
    appliance._logger = Mock()

    appliance.session.connected = True
    coordinator.connected = True
    coordinator.async_set_updated_data(None)
    await hass.async_block_till_done()
    # The state has not arrived yet
    assert hass.states.get(entity_id).state == STATE_UNKNOWN
    return appliance, coordinator, entity_id


async def _sync(
    hass: HomeAssistant, appliance: MockAppliance, synced_values: dict[int, int] | None
) -> None:
    """
    Run the library's sync of the appliance state: synced_values is uid -> raw value.

    None makes it fail because the connection is lost, as the library
    reports CONNECTED to the coordinator either way.
    """
    if synced_values is None:
        appliance.session.send_sync.side_effect = DisconnectedError
        appliance.session.connected = False
    else:
        responses = {
            "/ro/allDescriptionChanges": [],
            "/ro/allMandatoryValues": [
                {"uid": uid, "value": value} for uid, value in synced_values.items()
            ],
        }
        appliance.session.send_sync.side_effect = lambda message: Mock(
            data=responses[message.resource]
        )
        appliance.session.connected = True
    await appliance._connection_callback(ConnectionState.CONNECTED)
    await appliance._task_manager.block_till_done()
    await hass.async_block_till_done()


async def _connect_washer(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, synced_values: dict[int, int]
) -> tuple[MockAppliance, str]:
    """Set up a washer and connect it with an appliance state of synced_values."""
    appliance, coordinator, entity_id = await _setup_washer(hass, monkeypatch)
    await _sync(hass, appliance, synced_values)
    assert coordinator.synced
    return appliance, entity_id


async def test_first_sync_after_connecting_is_not_a_finish(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    The state delivered by the first sync is not a finish, however it differs from the profile.

    Until it has synced, the sensor only sees the defaults from the appliance
    profile. A washer that was already Finished then looks like it changed
    from Inactive to Finished, but it didn't finish just now.
    """
    appliance, entity_id = await _connect_washer(
        hass, monkeypatch, {OPERATION_STATE_DESCRIPTION["uid"]: FINISHED}
    )
    assert appliance.entities[OPERATION_STATE].value == "Finished"
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    # The same state again, or the event of the finish, are still that finish
    await _update(hass, appliance, OPERATION_STATE, FINISHED)
    await _update(hass, appliance, PROGRAM_FINISHED, PRESENT)
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    # A finish after that counts
    await _update(hass, appliance, PROGRAM_FINISHED, OFF)
    await _update(hass, appliance, OPERATION_STATE, RUN)
    assert hass.states.get(entity_id).state == STATE_UNKNOWN
    await _update(hass, appliance, OPERATION_STATE, FINISHED)
    assert datetime.fromisoformat(hass.states.get(entity_id).state)


async def test_finish_right_after_first_sync_is_recorded(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first change after the first sync counts even if nothing else updated in between."""
    appliance, entity_id = await _connect_washer(
        hass, monkeypatch, {OPERATION_STATE_DESCRIPTION["uid"]: RUN}
    )
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    await _update(hass, appliance, OPERATION_STATE, FINISHED)
    assert datetime.fromisoformat(hass.states.get(entity_id).state)


async def test_finish_after_first_sync_that_changed_nothing_is_recorded(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A finish counts even when the first sync brought no update for the sensor's signals."""
    appliance, entity_id = await _connect_washer(hass, monkeypatch, {})
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    await _update(hass, appliance, OPERATION_STATE, FINISHED)
    assert datetime.fromisoformat(hass.states.get(entity_id).state)


async def test_failed_first_sync_is_not_taken_as_the_state(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sync that failed because the connection was lost leaves only the profile defaults."""
    appliance, coordinator, entity_id = await _setup_washer(hass, monkeypatch)

    await _sync(hass, appliance, None)
    assert not coordinator.synced
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    # After reconnecting, the washer turns out to have been Finished all along
    await _sync(hass, appliance, {OPERATION_STATE_DESCRIPTION["uid"]: FINISHED})
    assert coordinator.synced
    assert appliance.entities[OPERATION_STATE].value == "Finished"
    assert hass.states.get(entity_id).state == STATE_UNKNOWN


async def test_finish_while_reconnecting_is_recorded(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    freezer: FrozenDateTimeFactory,
) -> None:
    """After a reconnect the appliance reports where it got to, a finish in there counts."""
    freezer.move_to(T0)
    appliance = _mock_appliance(monkeypatch)
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    entity_id = _entity_id(hass)
    entry: HCConfigEntry = hass.config_entries.async_entries(DOMAIN)[0]
    coordinator = entry.runtime_data.coordinator
    await _update(hass, appliance, OPERATION_STATE, RUN)

    appliance.session.connected = False
    coordinator.connected = False
    coordinator.async_set_updated_data(None)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    freezer.move_to(T0 + timedelta(hours=1))
    appliance.session.connected = True
    coordinator.connected = True
    await _update(hass, appliance, OPERATION_STATE, FINISHED)
    assert hass.states.get(entity_id).state == (T0 + timedelta(hours=1)).isoformat()


async def test_restores_last_finished(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The timestamp survives a restart, and an appliance still Finished doesn't replace it."""
    freezer.move_to(T0 + timedelta(days=1))
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State("sensor.fake_brand_homeappliance_last_finished", T0.isoformat()),
                {
                    "native_value": {
                        "__type": "<class 'datetime.datetime'>",
                        "isoformat": T0.isoformat(),
                    },
                    "native_unit_of_measurement": None,
                },
            ),
        ),
    )
    appliance = _mock_appliance(monkeypatch, operation_state=FINISHED)
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    entity_id = _entity_id(hass)
    assert entity_id == "sensor.fake_brand_homeappliance_last_finished"
    assert hass.states.get(entity_id).state == T0.isoformat()

    await _update(hass, appliance, OPERATION_STATE, RUN)
    freezer.move_to(T0 + timedelta(days=1, hours=1))
    await _update(hass, appliance, OPERATION_STATE, FINISHED)
    assert hass.states.get(entity_id).state == (T0 + timedelta(days=1, hours=1)).isoformat()


async def test_ignores_unusable_restored_value(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A restored value that isn't a timezone aware timestamp is dropped, not shown."""
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State("sensor.fake_brand_homeappliance_last_finished", "2026-10-07T12:00:00"),
                {
                    "native_value": {
                        "__type": "<class 'datetime.datetime'>",
                        "isoformat": "2026-10-07T12:00:00",
                    },
                    "native_unit_of_measurement": None,
                },
            ),
        ),
    )
    _mock_appliance(monkeypatch)
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    assert hass.states.get(_entity_id(hass)).state == STATE_UNKNOWN


async def test_created_for_appliance_without_finished_signal(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every appliance gets the sensor, one with nothing to watch just stays unknown."""
    appliance = _mock_appliance(monkeypatch, operation_state=None, program_finished=False)
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    state = hass.states.get(_entity_id(hass))
    assert state
    assert state.state == STATE_UNKNOWN
    assert generate_last_finished(appliance).entities == []


async def test_description_watches_the_finished_signals_the_appliance_has(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the finished signals the appliance actually has are watched."""
    both = _mock_appliance(monkeypatch)
    assert generate_last_finished(both).entities == [OPERATION_STATE, PROGRAM_FINISHED]

    state_only = _mock_appliance(monkeypatch, program_finished=False)
    assert generate_last_finished(state_only).entities == [OPERATION_STATE]

    event_only = _mock_appliance(monkeypatch, operation_state=None)
    assert generate_last_finished(event_only).entities == [PROGRAM_FINISHED]

    # ...and it is part of what every appliance gets
    for appliance in (both, state_only, event_only):
        descriptions = get_available_entities(appliance)["last_finished"]
        assert [description.key for description in descriptions] == ["sensor_last_finished"]
    bare = _mock_appliance(monkeypatch, operation_state=None, program_finished=False)
    descriptions = get_available_entities(bare)["last_finished"]
    assert [description.key for description in descriptions] == ["sensor_last_finished"]


def test_finished_values_are_the_states_the_binary_sensor_uses() -> None:
    """The finished event counts as on for the same values as the Program Finished sensor."""
    from custom_components.homeconnect_ws.entity_descriptions.common import (  # noqa: PLC0415
        COMMON_ENTITY_DESCRIPTIONS,
    )

    binary_sensor = next(
        description
        for description in COMMON_ENTITY_DESCRIPTIONS["binary_sensor"]
        if getattr(description, "key", None) == "binary_sensor_program_finished"
    )
    assert binary_sensor.entity == PROGRAM_FINISHED
    assert set(binary_sensor.value_on) == LAST_FINISHED_VALUES[PROGRAM_FINISHED]


def test_last_finished_is_translated_and_has_an_icon() -> None:
    """The generated description has an English and German name and an icon."""
    integration = Path("custom_components/homeconnect_ws")
    for language in ("en", "de"):
        translations = json.loads(
            (integration / "translations" / f"{language}.json").read_text(encoding="utf-8")
        )
        assert translations["entity"]["sensor"]["sensor_last_finished"]["name"]
    icons = json.loads((integration / "icons.json").read_text(encoding="utf-8"))
    assert icons["entity"]["sensor"]["sensor_last_finished"]["default"]
