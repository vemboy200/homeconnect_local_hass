"""Tests for integration init."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from ipaddress import ip_address
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import ANY, AsyncMock, Mock

from custom_components.homeconnect_ws import coordinator
from custom_components.homeconnect_ws.const import (
    CONF_APPLIANCE_INFO,
    CONF_DESCRIPTION_FILENAME,
    CONF_FEATURE_FILENAME,
    DOMAIN,
)
from home_disconnect import ConnectionFailedError, parse_device_description
from home_disconnect.testutils import MockAppliance
from homeassistant.config_entries import SOURCE_ZEROCONF, ConfigEntryState
from homeassistant.const import CONF_DESCRIPTION, CONF_HOST
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.helpers.storage import STORAGE_DIR
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .const import DEVICE_DESCRIPTION, MOCK_APPLIANCE_INFO, MOCK_CONFIG_DATA, MOCK_TLS_DEVICE_ID

if TYPE_CHECKING:
    import pytest
    from homeassistant.core import HomeAssistant


async def test_load_unload_entry(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test setup and unload config entry."""
    appliance = MockAppliance(DEVICE_DESCRIPTION, "host", "mock_app", "mock_app_id", "PSK_KEY")
    appliance_mock = Mock(return_value=appliance)
    monkeypatch.setattr(coordinator, "HomeAppliance", appliance_mock)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG_DATA,
        unique_id=MOCK_TLS_DEVICE_ID,
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    appliance_mock.assert_called_once_with(
        description=DEVICE_DESCRIPTION,
        host="1.2.3.4",
        app_name="Homeassistant",
        app_id="Test_Device_ID",
        psk64="PSK_KEY",
        iv64="AES_IV",
        session=ANY,
        connection_callback=ANY,
        reconect=True,
    )

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED

    appliance.session.close.assert_awaited_once()


async def test_migrate_entry_v1_to_v2(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Test a v1 config entry migrates to v2 storage on setup.

    v2 matches upstream chris-mc1/homeconnect_local_hass's schema exactly
    (CONF_APPLIANCE_INFO + XML files under storage_dir/{deviceID}/) so a
    future upstream merge doesn't have to reconcile two different "v2"
    shapes. CONF_DESCRIPTION is deliberately kept alongside the new keys -
    coordinator.py still reads it directly, and switching that over is a
    separate follow-up - so this only checks the migration itself is
    correct, not that the old key gets dropped.
    """
    appliance = MockAppliance(DEVICE_DESCRIPTION, "host", "mock_app", "mock_app_id", "PSK_KEY")
    appliance_mock = Mock(return_value=appliance)
    monkeypatch.setattr(coordinator, "HomeAppliance", appliance_mock)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG_DATA,
        unique_id=MOCK_TLS_DEVICE_ID,
        version=1,
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.version == 2

    device_id = MOCK_APPLIANCE_INFO["deviceID"]
    assert entry.data[CONF_APPLIANCE_INFO] == MOCK_APPLIANCE_INFO
    assert entry.data[CONF_DESCRIPTION_FILENAME] == f"{device_id}/DeviceDescription.xml"
    assert entry.data[CONF_FEATURE_FILENAME] == f"{device_id}/FeatureMapping.xml"
    # Kept, not dropped - coordinator.py still reads this directly.
    assert entry.data[CONF_DESCRIPTION] == DEVICE_DESCRIPTION

    # Round-trip fidelity of serialize_device_description()/
    # parse_device_description() themselves is home-disconnect's own
    # concern (covered by its own test suite) - this only checks the
    # migration actually wrote real, parseable XML, not that every field/
    # entity survives serialization byte-for-byte.
    storage_dir = Path(hass.config.path(STORAGE_DIR, DOMAIN))
    description_xml = (storage_dir / entry.data[CONF_DESCRIPTION_FILENAME]).read_text()
    feature_xml = (storage_dir / entry.data[CONF_FEATURE_FILENAME]).read_text()
    reloaded = parse_device_description(description_xml, feature_xml)
    assert reloaded["status"]
    assert reloaded["setting"]


async def test_device_registry_serial_number(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test the device registry entry exposes the appliance's serial number."""
    appliance = MockAppliance(DEVICE_DESCRIPTION, "host", "mock_app", "mock_app_id", "PSK_KEY")
    monkeypatch.setattr(coordinator, "HomeAppliance", Mock(return_value=appliance))

    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG_DATA,
        unique_id=MOCK_TLS_DEVICE_ID,
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.unique_id)})
    assert device is not None
    assert device.serial_number == MOCK_APPLIANCE_INFO["serialNumber"]


async def test_setup_entry_washer_connect_failure_is_non_blocking(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Standalone washers/dryers keep the non-blocking setup even if unreachable."""
    description = deepcopy(DEVICE_DESCRIPTION)
    description["info"]["type"] = "Washer"
    appliance = MockAppliance(description, "host", "mock_app", "mock_app_id", "PSK_KEY")
    appliance.session.connect = AsyncMock(side_effect=ConnectionFailedError)
    appliance_mock = Mock(return_value=appliance)
    monkeypatch.setattr(coordinator, "HomeAppliance", appliance_mock)

    # The mock appliance above is decoupled from what the config entry itself
    # carries (HomeAppliance is fully replaced by appliance_mock, which
    # ignores its description= kwarg) - coordinator.py reads the appliance
    # type from config_entry.data, not from the constructed appliance, so
    # the entry's own description needs the same type override too.
    config_data = deepcopy(MOCK_CONFIG_DATA)
    config_data[CONF_DESCRIPTION] = description
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=config_data,
        unique_id=MOCK_TLS_DEVICE_ID,
    )
    entry.add_to_hass(hass)

    # Not async_block_till_done(): the exempt path's _connect() retries in a
    # background task with real asyncio.sleep() backoff, which would hang
    # this waiting for it. _async_setup() itself returns immediately after
    # scheduling that task, so entry.state is already settled by this point.
    await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.LOADED

    await hass.config_entries.async_unload(entry.entry_id)


async def test_washer_expected_offline_on_fresh_restart(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A fresh HA restart must not make a simply-off washer look broken.

    Confirmed live on fork issue #7: entities showed Unavailable after every
    HA restart while the washer was just powered off, since last_close_code
    lives on the in-memory session and resets to None on every fresh
    process start - before this process has witnessed any close code at
    all, let alone specifically 1000. expected_offline used to require
    proof of a clean code-1000 close, so "no evidence yet" was wrongly
    treated the same as "known bad".
    """
    description = deepcopy(DEVICE_DESCRIPTION)
    description["info"]["type"] = "Washer"
    appliance = MockAppliance(description, "host", "mock_app", "mock_app_id", "PSK_KEY")
    appliance.session.connect = AsyncMock(side_effect=ConnectionFailedError)
    appliance.session.connected = False
    appliance.session.last_close_code = None
    appliance_mock = Mock(return_value=appliance)
    monkeypatch.setattr(coordinator, "HomeAppliance", appliance_mock)

    config_data = deepcopy(MOCK_CONFIG_DATA)
    config_data[CONF_DESCRIPTION] = description
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=config_data,
        unique_id=MOCK_TLS_DEVICE_ID,
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    coord = entry.runtime_data.coordinator

    assert coord.expected_offline is True

    # A confirmed non-clean close code still correctly reports as not expected.
    appliance.session.last_close_code = 1006
    assert coord.expected_offline is False

    # Actually connected must never read as expected_offline, regardless of
    # last_close_code - confirmed live on fork issue #21: home_disconnect
    # resets last_close_code back to None the moment a connection succeeds,
    # so a fully-connected, always-online washer was getting force_off_*/
    # clear_on_expected_offline entities (switch_power_state,
    # sensor_power_state, ...) stuck at their offline placeholder forever.
    appliance.session.connected = True
    appliance.session.last_close_code = None
    assert coord.expected_offline is False
    appliance.session.last_close_code = 1000
    assert coord.expected_offline is False


async def test_washer_background_connect_does_not_block_till_done(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    async_block_till_done() must not wait on the exempt-type connect loop.

    Confirmed live on fork issue #16: using async_create_task() for this
    background loop meant it was tracked and waited on by Home Assistant's
    own startup sequencing, blocking the rest of HA's bootstrap for minutes
    whenever a washer/dryer was unreachable at startup - the loop retries
    with backoff for as long as the appliance stays off. Switched to
    async_create_background_task(), which is documented not to block
    startup and not be waited on by async_block_till_done().
    """
    description = deepcopy(DEVICE_DESCRIPTION)
    description["info"]["type"] = "Washer"
    appliance = MockAppliance(description, "host", "mock_app", "mock_app_id", "PSK_KEY")
    appliance.session.connect = AsyncMock(side_effect=ConnectionFailedError)
    appliance_mock = Mock(return_value=appliance)
    monkeypatch.setattr(coordinator, "HomeAppliance", appliance_mock)

    config_data = deepcopy(MOCK_CONFIG_DATA)
    config_data[CONF_DESCRIPTION] = description
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=config_data,
        unique_id=MOCK_TLS_DEVICE_ID,
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.LOADED

    # The connect loop is still retrying in the background (the mock always
    # fails) - if it were still tracked by async_create_task(), this would
    # hang for the loop's full backoff schedule instead of returning almost
    # immediately.
    await asyncio.wait_for(hass.async_block_till_done(), timeout=2)

    await hass.config_entries.async_unload(entry.entry_id)


async def test_setup_entry_non_laundry_connect_failure_not_ready(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Non-laundry appliances raise ConfigEntryNotReady if unreachable at setup.

    Raised as UpdateFailed, not ConfigEntryNotReady directly - confirmed live
    on fork issue #30: ConfigEntryNotReady isn't a ConfigEntryError subclass,
    so HA's own __wrap_async_setup() doesn't recognize it as an expected
    setup failure and logs a full ERROR-level traceback via "Unexpected
    error fetching %s data" on every single retry while the appliance stays
    unreachable, before discarding it and raising its own ConfigEntryNotReady
    anyway. UpdateFailed is handled quietly and still ends up as
    ConfigEntryNotReady for the config entry.
    """
    monkeypatch.setattr(coordinator, "SETUP_CONNECT_RETRY_DELAY", 0)
    appliance = MockAppliance(DEVICE_DESCRIPTION, "host", "mock_app", "mock_app_id", "PSK_KEY")
    appliance.session.connect = AsyncMock(side_effect=ConnectionFailedError)
    appliance_mock = Mock(return_value=appliance)
    monkeypatch.setattr(coordinator, "HomeAppliance", appliance_mock)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG_DATA,
        unique_id=MOCK_TLS_DEVICE_ID,
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    # Every attempt was exhausted, not just one, before giving up.
    assert appliance.session.connect.await_count == coordinator.SETUP_CONNECT_ATTEMPTS
    assert "Unexpected error fetching" not in caplog.text


async def test_setup_entry_non_laundry_retries_transient_connect_failure(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single momentary connect failure at setup is retried, not fatal on its own."""
    monkeypatch.setattr(coordinator, "SETUP_CONNECT_RETRY_DELAY", 0)
    appliance = MockAppliance(DEVICE_DESCRIPTION, "host", "mock_app", "mock_app_id", "PSK_KEY")
    appliance.session.connect = AsyncMock(side_effect=[ConnectionFailedError, None])
    appliance_mock = Mock(return_value=appliance)
    monkeypatch.setattr(coordinator, "HomeAppliance", appliance_mock)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG_DATA,
        unique_id=MOCK_TLS_DEVICE_ID,
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert appliance.session.connect.await_count == 2


async def test_washer_reconnect_poll_registered_and_recovers(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    The fallback poll is registered for standalone washers/dryers and recovers connectivity.

    home-disconnect's own auto-reconnect is disabled for these (reconect=
    False), so nothing else would notice the appliance coming back after
    the initial connect fails.
    """
    description = deepcopy(DEVICE_DESCRIPTION)
    description["info"]["type"] = "Washer"
    appliance = MockAppliance(description, "host", "mock_app", "mock_app_id", "PSK_KEY")
    appliance.session.connect = AsyncMock(side_effect=ConnectionFailedError)
    appliance_mock = Mock(return_value=appliance)
    monkeypatch.setattr(coordinator, "HomeAppliance", appliance_mock)

    config_data = deepcopy(MOCK_CONFIG_DATA)
    config_data[CONF_DESCRIPTION] = description
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=config_data,
        unique_id=MOCK_TLS_DEVICE_ID,
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.LOADED
    coord = entry.runtime_data.coordinator
    assert coord._poll_unsub is not None
    assert coord.connected is False

    # Appliance is reachable again - call the poll directly rather than
    # waiting out the real 20s interval or racing _connect()'s own
    # background retry loop (still running with the old failing mock).
    appliance.session.connect = AsyncMock()
    appliance.session.connected = True
    await coord._async_poll_reconnect(dt_util.utcnow())

    assert coord.connected is True

    await hass.config_entries.async_unload(entry.entry_id)
    assert coord._poll_unsub is None


async def test_nudge_reconnect_schedules_immediate_retry_for_disconnected_washer(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """async_nudge_reconnect() (called from the zeroconf discovery flow) retries now."""
    description = deepcopy(DEVICE_DESCRIPTION)
    description["info"]["type"] = "Washer"
    appliance = MockAppliance(description, "host", "mock_app", "mock_app_id", "PSK_KEY")
    appliance.session.connect = AsyncMock(side_effect=ConnectionFailedError)
    appliance_mock = Mock(return_value=appliance)
    monkeypatch.setattr(coordinator, "HomeAppliance", appliance_mock)

    config_data = deepcopy(MOCK_CONFIG_DATA)
    config_data[CONF_DESCRIPTION] = description
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=config_data,
        unique_id=MOCK_TLS_DEVICE_ID,
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    coord = entry.runtime_data.coordinator
    assert coord.connected is False

    appliance.session.connect = AsyncMock()
    appliance.session.connected = True
    coord.async_nudge_reconnect()
    # async_nudge_reconnect() schedules its retry via
    # async_create_background_task() (see coordinator.py - deliberately not
    # tracked by HA's startup sequencing), so a plain async_block_till_done()
    # isn't guaranteed to wait for it. Whether it happens to finish in time
    # anyway depends on unrelated event-loop scheduling, which is exactly
    # the kind of thing that can differ between HA versions - explicitly
    # opt in to waiting for it instead of relying on that.
    await hass.async_block_till_done(wait_background_tasks=True)

    assert coord.connected is True


async def test_nudge_reconnect_is_noop_when_already_connected(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A redundant re-announcement while already connected doesn't trigger another connect."""
    description = deepcopy(DEVICE_DESCRIPTION)
    description["info"]["type"] = "Washer"
    appliance = MockAppliance(description, "host", "mock_app", "mock_app_id", "PSK_KEY")
    appliance_mock = Mock(return_value=appliance)
    monkeypatch.setattr(coordinator, "HomeAppliance", appliance_mock)

    config_data = deepcopy(MOCK_CONFIG_DATA)
    config_data[CONF_DESCRIPTION] = description
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=config_data,
        unique_id=MOCK_TLS_DEVICE_ID,
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    coord = entry.runtime_data.coordinator
    assert coord.connected is True

    connect_calls_before = appliance.session.connect.call_count
    coord.async_nudge_reconnect()
    await hass.async_block_till_done()

    assert appliance.session.connect.call_count == connect_calls_before


async def test_nudge_reconnect_is_noop_for_non_exempt_appliance(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
) -> None:
    """A dishwasher's coordinator ignores the nudge - not in the exempt/disconnect-prone set."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG_DATA,
        unique_id=MOCK_TLS_DEVICE_ID,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    coord = entry.runtime_data.coordinator

    connect_calls_before = mock_appliance.session.connect.call_count
    coord.async_nudge_reconnect()
    await hass.async_block_till_done()

    assert mock_appliance.session.connect.call_count == connect_calls_before


async def test_setup_entry_washer_dryer_combo_connect_failure_is_non_blocking(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    WasherDryer combos are exempt, same as standalone washers/dryers.

    Combo behavior isn't consistent across models - one checked (WNC254A0BY)
    stays connected while powered off, but upstream issue #426 confirms
    another (WDU28512) drops offline like a standalone unit. Included in the
    exemption either way, since it's harmless for a model that happens to
    stay connected - the previous "not exempt" behavior gave WDU28512-style
    combos a false setup error whenever they were simply powered off.
    """
    description = deepcopy(DEVICE_DESCRIPTION)
    description["info"]["type"] = "WasherDryer"
    appliance = MockAppliance(description, "host", "mock_app", "mock_app_id", "PSK_KEY")
    appliance.session.connect = AsyncMock(side_effect=ConnectionFailedError)
    appliance_mock = Mock(return_value=appliance)
    monkeypatch.setattr(coordinator, "HomeAppliance", appliance_mock)

    config_data = deepcopy(MOCK_CONFIG_DATA)
    config_data[CONF_DESCRIPTION] = description
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=config_data,
        unique_id=MOCK_TLS_DEVICE_ID,
    )
    entry.add_to_hass(hass)

    # Not async_block_till_done(): the exempt path's _connect() retries in a
    # background task with real asyncio.sleep() backoff, which would hang
    # this waiting for it. _async_setup() itself returns immediately after
    # scheduling that task, so entry.state is already settled by this point.
    await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.LOADED

    await hass.config_entries.async_unload(entry.entry_id)


def _make_zeroconf_discovery_info(host: str) -> ZeroconfServiceInfo:
    return ZeroconfServiceInfo(
        ip_address=ip_address(host),
        ip_addresses=[ip_address(host)],
        port=80,
        hostname="mock-host.local.",
        type="_homeconnect._tcp.local.",
        name="MOCK-NAME._homeconnect._tcp.local.",
        properties={
            "id": MOCK_TLS_DEVICE_ID,
            "vib": "Fake_vib",
            "brand": "Fake_Brand",
            "type": "Washer",
        },
    )


async def test_zeroconf_nudges_reconnect_for_loaded_laundry_entry(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-announcing at the same IP nudges an immediate reconnect, not just a reload."""
    description = deepcopy(DEVICE_DESCRIPTION)
    description["info"]["type"] = "Washer"
    appliance = MockAppliance(description, "host", "mock_app", "mock_app_id", "PSK_KEY")
    appliance.session.connect = AsyncMock(side_effect=ConnectionFailedError)
    appliance_mock = Mock(return_value=appliance)
    monkeypatch.setattr(coordinator, "HomeAppliance", appliance_mock)

    config_data = deepcopy(MOCK_CONFIG_DATA)
    config_data[CONF_DESCRIPTION] = description
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=config_data,
        unique_id=MOCK_TLS_DEVICE_ID,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)

    coord = entry.runtime_data.coordinator
    assert coord.connected is False

    # Appliance is reachable again by the time it re-announces itself.
    appliance.session.connect = AsyncMock()
    appliance.session.connected = True

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_ZEROCONF},
        data=_make_zeroconf_discovery_info(config_data[CONF_HOST]),
    )
    # Same as test_nudge_reconnect_schedules_immediate_retry_for_disconnected_washer:
    # the nudge's retry runs via async_create_background_task(), not waited on by
    # async_block_till_done() unless explicitly requested.
    await hass.async_block_till_done(wait_background_tasks=True)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert coord.connected is True


async def test_zeroconf_does_not_nudge_unloaded_entry(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No coordinator to nudge (and no crash) when the matching entry isn't loaded."""
    description = deepcopy(DEVICE_DESCRIPTION)
    description["info"]["type"] = "Washer"
    appliance = MockAppliance(description, "host", "mock_app", "mock_app_id", "PSK_KEY")
    appliance_mock = Mock(return_value=appliance)
    monkeypatch.setattr(coordinator, "HomeAppliance", appliance_mock)

    config_data = deepcopy(MOCK_CONFIG_DATA)
    config_data[CONF_DESCRIPTION] = description
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=config_data,
        unique_id=MOCK_TLS_DEVICE_ID,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.config_entries.async_unload(entry.entry_id)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_ZEROCONF},
        data=_make_zeroconf_discovery_info(config_data[CONF_HOST]),
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_concurrent_reconnect_attempts_are_serialized(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Two overlapping reconnect triggers don't race each other.

    Without _connect_lock, a second caller arriving while the first's
    appliance.connect() is still in flight would raise AllreadyConnectedError
    and react by closing the shared session - tearing down the first
    caller's in-progress connection too. Confirms only one connect() call
    ever happens even when two triggers overlap.
    """
    description = deepcopy(DEVICE_DESCRIPTION)
    description["info"]["type"] = "Washer"
    appliance = MockAppliance(description, "host", "mock_app", "mock_app_id", "PSK_KEY")

    connect_started = asyncio.Event()
    release_connect = asyncio.Event()
    connect_call_count = 0

    async def slow_connect() -> None:
        nonlocal connect_call_count
        connect_call_count += 1
        connect_started.set()
        await release_connect.wait()
        appliance.session.connected = True

    appliance.session.connect = AsyncMock(side_effect=slow_connect)
    appliance_mock = Mock(return_value=appliance)
    monkeypatch.setattr(coordinator, "HomeAppliance", appliance_mock)

    config_data = deepcopy(MOCK_CONFIG_DATA)
    config_data[CONF_DESCRIPTION] = description
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=config_data,
        unique_id=MOCK_TLS_DEVICE_ID,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    coord = entry.runtime_data.coordinator

    # Wait for the background _connect() task's first attempt to actually
    # start and block (holding _connect_lock).
    await connect_started.wait()
    assert coord.connected is False

    # A second trigger fires while the first is still in flight - it must
    # wait for the lock rather than racing in with its own connect() call.
    poll_task = asyncio.ensure_future(coord._async_poll_reconnect(dt_util.utcnow()))
    await asyncio.sleep(0)
    assert connect_call_count == 1

    release_connect.set()
    await poll_task
    await hass.async_block_till_done()

    # The second caller saw self.connected already True once it finally got
    # the lock, and returned without calling connect() again.
    assert connect_call_count == 1
    assert coord.connected is True

    await hass.config_entries.async_unload(entry.entry_id)
