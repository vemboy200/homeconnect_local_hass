"""Tests for the profile export ZIP builder."""

from __future__ import annotations

import json
import zipfile
from io import BytesIO

from custom_components.homeconnect_ws.export_profile import build_profile_zip, filename_stub
from home_disconnect import parse_device_description
from homeassistant.const import CONF_MODE
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .const import MOCK_CONFIG_DATA


def _make_entry() -> MockConfigEntry:
    data = {**MOCK_CONFIG_DATA, CONF_MODE: "AES"}
    return MockConfigEntry(domain="homeconnect_ws", data=data, unique_id="Test_haId")


def test_filename_stub() -> None:
    """Filenames use lowercase brand + vib, not the MAC-based original."""
    entry = _make_entry()
    assert filename_stub(entry) == "fake_brand_Fake_vib"


def test_build_profile_zip_full_includes_key() -> None:
    """The Full export includes the local encryption key and re-parses correctly."""
    entry = _make_entry()
    zip_bytes = build_profile_zip(entry, True)  # noqa: FBT003

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zip_file:
        names = zip_file.namelist()
        assert "fake_brand_Fake_vib_DeviceDescription.xml" in names
        assert "fake_brand_Fake_vib_FeatureMapping.xml" in names
        assert "fake_brand_Fake_vib.json" in names

        profile = json.loads(zip_file.read("fake_brand_Fake_vib.json"))
        assert profile["haId"] == "Test_haId"
        assert profile["key"] == "PSK_KEY"
        assert profile["iv"] == "AES_IV"
        assert profile["deviceDescriptionFileName"] == "fake_brand_Fake_vib_DeviceDescription.xml"
        assert profile["featureMappingFileName"] == "fake_brand_Fake_vib_FeatureMapping.xml"

        description = parse_device_description(
            zip_file.read("fake_brand_Fake_vib_DeviceDescription.xml"),
            zip_file.read("fake_brand_Fake_vib_FeatureMapping.xml"),
        )
        assert description["info"]["brand"] == "Fake_Brand"


def test_build_profile_zip_safe_omits_key() -> None:
    """The Safe export has no key/json file and stays re-parseable."""
    entry = _make_entry()
    zip_bytes = build_profile_zip(entry, False)  # noqa: FBT003

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zip_file:
        names = zip_file.namelist()
        assert "fake_brand_Fake_vib_DeviceDescription.xml" in names
        assert "fake_brand_Fake_vib_FeatureMapping.xml" in names
        assert not any(name.endswith(".json") for name in names)

        description = parse_device_description(
            zip_file.read("fake_brand_Fake_vib_DeviceDescription.xml"),
            zip_file.read("fake_brand_Fake_vib_FeatureMapping.xml"),
        )
        assert description["info"]["brand"] == "Fake_Brand"
