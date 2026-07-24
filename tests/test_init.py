"""Tests for integration init."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from ipaddress import ip_address
from typing import TYPE_CHECKING
from unittest.mock import ANY, AsyncMock, Mock

from custom_components.homeconnect_ws import coordinator
from custom_components.homeconnect_ws.const import DOMAIN
from home_disconnect import ConnectionFailedError
from home_disconnect.testutils import MockAppliance
from homeassistant.config_entries import SOURCE_ZEROCONF, ConfigEntryState
from homeassistant.const import CONF_DESCRIPTION, CONF_HOST
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .const import DEVICE_DESCRIPTION, MOCK_CONFIG_DATA, MOCK_TLS_DEVICE_ID

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


async def test_setup_entry_non_laundry_connect_failure_not_ready(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-laundry appliances raise ConfigEntryNotReady if unreachable at setup."""
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
    await hass.async_block_till_done()

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


async def test_setup_entry_washer_dryer_combo_is_blocking(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WasherDryer combos are not exempt - the one checked (WNC254A0BY) stays online while off."""
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

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY


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
    await hass.async_block_till_done()

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
