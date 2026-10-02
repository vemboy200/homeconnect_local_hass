"""Tests for the diagnostics platform (the Safe export's native equivalent)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from custom_components.homeconnect_ws.diagnostics import async_get_config_entry_diagnostics

from . import setup_config_entry
from .const import MOCK_CONFIG_DATA

if TYPE_CHECKING:
    from home_disconnect.testutils import MockAppliance
    from homeassistant.core import HomeAssistant


async def test_diagnostics_returns_safe_profile(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """Diagnostics returns the two profile XML files and basic device info, no key/MAC/serial."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    entry = hass.config_entries.async_entries("homeconnect_ws")[0]
    mock_appliance.session.service_versions = {}

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["brand"] == "Fake_Brand"
    assert result["model"] == "Fake_vib"
    assert "<device>" in result["device_description_xml"]
    assert result["feature_mapping_xml"]

    dumped = str(result)
    assert "PSK_KEY" not in dumped
    assert "AES_IV" not in dumped


async def test_diagnostics_still_includes_redacted_entry_data_and_live_state(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,
    patch_entity_description: None,
) -> None:
    """
    Diagnostics keeps its original entry_data/appliance_state fields alongside the new XML ones.

    This platform already existed (pre-dating the Safe-export-via-diagnostics
    change) for exactly the bug-report use case - redacted config entry data
    plus a live snapshot of every entity's current value. Adding the XML
    fields is additive, not a replacement.
    """
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    entry = hass.config_entries.async_entries("homeconnect_ws")[0]
    mock_appliance.session.service_versions = {}

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["entry_data"]["psk"] == "**REDACTED**"
    assert "appliance_state" in result
