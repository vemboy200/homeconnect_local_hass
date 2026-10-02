"""Tests for HomeConnectCoordinator."""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.homeconnect_ws.const import DOMAIN
from home_disconnect.message import Message

from . import setup_config_entry
from .const import MOCK_CONFIG_DATA

if TYPE_CHECKING:
    from home_disconnect.testutils import MockAppliance
    from homeassistant.core import HomeAssistant

_SAMPLE_NETWORK_INFO = [
    {
        "interfaceID": 0,
        "type": "WiFi",
        "rssi": -73,
        "ipV4": {
            "ipAddress": "192.168.1.50",
            "prefixSize": 24,
            "gateway": "192.168.1.1",
            "dnsServer": "192.168.1.1",
        },
    }
]


async def test_async_get_network_info_skips_when_not_connected(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """
    Must not attempt a request before the appliance has connected.

    Entities can be added (and their immediate poll-on-add fired) before the
    appliance's first handshake completes, since setup doesn't block on a
    successful connection. Polling anyway used to crash deep in
    home_disconnect's message-ID counter, which is only initialized once the
    handshake finishes - this guard is what HCWiFI's async_update used to do
    itself before the ipv4/ipv6 sensors needed to share it too.
    """
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    mock_appliance.session.connected = False
    mock_appliance.session.send_sync.reset_mock()

    result = await entry.runtime_data.coordinator.async_get_network_info()

    assert result is None
    mock_appliance.session.send_sync.assert_not_called()


async def test_async_get_network_info_fetches_once_connected(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Returns whatever /ni/info responds with once connected."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    mock_appliance.session.send_sync.reset_mock()
    mock_appliance.session.send_sync.return_value = Message(
        resource="/ni/info", data=_SAMPLE_NETWORK_INFO
    )

    result = await entry.runtime_data.coordinator.async_get_network_info()

    assert result == _SAMPLE_NETWORK_INFO


async def test_async_get_network_info_coalesces_concurrent_calls(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """
    A second call shortly after the first reuses its result, not a new request.

    HCWiFI and the ipv4/ipv6 address sensors are all should_poll entities on
    the same SCAN_INTERVAL, so they'd otherwise each fire their own /ni/info
    request every time that timer elapses - this is what actually collapses
    those three into one round trip to the appliance.
    """
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    mock_appliance.session.send_sync.reset_mock()
    mock_appliance.session.send_sync.return_value = Message(
        resource="/ni/info", data=_SAMPLE_NETWORK_INFO
    )
    coordinator = entry.runtime_data.coordinator

    first = await coordinator.async_get_network_info()
    mock_appliance.session.send_sync.reset_mock()
    second = await coordinator.async_get_network_info()

    assert first == second == _SAMPLE_NETWORK_INFO
    mock_appliance.session.send_sync.assert_not_called()
