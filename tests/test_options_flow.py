"""Tests for the export options flow."""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

from home_disconnect import parse_profile
from homeassistant.const import CONF_MODE
from homeassistant.data_entry_flow import FlowResultType

from . import setup_config_entry
from .const import MOCK_CONFIG_DATA

if TYPE_CHECKING:
    from home_disconnect import Appliance
    from homeassistant.core import HomeAssistant


async def test_options_flow_init_does_not_write_without_confirmation(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_entity_description: None,
) -> None:
    """
    Opening "Configure" alone must not write the key-bearing ZIP to disk.

    Confirmed live: before this confirmation step existed, opening the
    options flow for any reason - even just to see what's there - silently
    wrote the Full profile (including the real encryption key) to disk with
    no explicit action taken.
    """
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    entry = hass.config_entries.async_entries("homeconnect_ws")[0]

    with patch(
        "homeassistant.core.ServiceRegistry.async_call", new_callable=AsyncMock
    ) as mock_call:
        result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    mock_call.assert_not_awaited()


async def test_options_flow_writes_full_profile_zip_after_confirmation(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_entity_description: None,
) -> None:
    """Submitting the confirmation form writes the Full profile ZIP and says where."""
    assert await setup_config_entry(hass, {**MOCK_CONFIG_DATA, CONF_MODE: "AES"})
    entry = hass.config_entries.async_entries("homeconnect_ws")[0]

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})

    # The result is shown in the dialog, from options.abort in the translations.
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "export_written"
    assert result["description_placeholders"] == {
        "filename": "fake_brand_Fake_vib_profile_full.zip"
    }

    written = Path(
        hass.config.path("homeconnect_ws_export", "fake_brand_Fake_vib_profile_full.zip")
    )
    with zipfile.ZipFile(BytesIO(written.read_bytes())) as zip_file:  # noqa: ASYNC240
        assert sorted(zip_file.namelist()) == [
            "fake_brand_Fake_vib.json",
            "fake_brand_Fake_vib_DeviceDescription.xml",
            "fake_brand_Fake_vib_FeatureMapping.xml",
        ]
        profile = json.loads(zip_file.read("fake_brand_Fake_vib.json"))
        assert profile["haId"] == entry.unique_id
        assert profile["key"] == "PSK_KEY"
        assert profile["iv"] == "AES_IV"
        parsed = parse_profile(
            zip_file.read("fake_brand_Fake_vib_DeviceDescription.xml").decode(),
            zip_file.read("fake_brand_Fake_vib_FeatureMapping.xml").decode(),
        )
        assert parsed.info.brand == "Fake_Brand"


async def test_options_flow_notifies_on_write_failure(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_entity_description: None,
) -> None:
    """An OSError while writing the export file is reported in the dialog, not raised."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    entry = hass.config_entries.async_entries("homeconnect_ws")[0]

    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch("pathlib.Path.mkdir", side_effect=OSError("disk full")):
        result = await hass.config_entries.options.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "export_failed"
    assert result["description_placeholders"] == {"error": "disk full"}
