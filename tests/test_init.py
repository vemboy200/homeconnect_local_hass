"""Tests for integration init."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING
from unittest.mock import ANY, AsyncMock, Mock

from custom_components.homeconnect_ws import coordinator
from custom_components.homeconnect_ws.const import DOMAIN
from home_disconnect import ConnectionFailedError
from home_disconnect.testutils import MockAppliance
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_DESCRIPTION
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
