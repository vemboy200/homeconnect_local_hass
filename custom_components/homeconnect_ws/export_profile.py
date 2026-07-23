"""Build downloadable ZIP exports of an appliance's profile."""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from typing import TYPE_CHECKING

from home_disconnect import serialize_device_description
from homeassistant.const import CONF_DESCRIPTION, CONF_MODE

from .const import CONF_AES_IV, CONF_PSK

if TYPE_CHECKING:
    from . import HCConfigEntry


def filename_stub(config_entry: HCConfigEntry) -> str:
    """Build a `{brand}_{model}` filename stub instead of the MAC-based original."""
    info = config_entry.data[CONF_DESCRIPTION]["info"]
    brand = (info.get("brand") or "unknown").lower()
    model = info.get("vib") or info.get("model") or info.get("type") or "appliance"
    return f"{brand}_{model}"


def build_profile_zip(config_entry: HCConfigEntry, full: bool) -> bytes:  # noqa: FBT001
    """
    Build a ZIP export of the appliance's profile.

    full=True includes the local encryption key (a `.json` file matching the
    shape process_zip_file()/the Profile Downloader tool produce, so it can be
    re-imported via the Upload Profile File setup path). full=False omits the
    key entirely and is safe to share (e.g. attaching to a feature-request
    issue) - the XML content itself never contains the key, MAC, or serial
    number in either variant, only the omitted `.json` file does.
    """
    description = config_entry.data[CONF_DESCRIPTION]
    info = description["info"]
    stub = filename_stub(config_entry)
    description_filename = f"{stub}_DeviceDescription.xml"
    feature_filename = f"{stub}_FeatureMapping.xml"

    device_description_xml, feature_mapping_xml = serialize_device_description(description)

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr(description_filename, device_description_xml)
        zip_file.writestr(feature_filename, feature_mapping_xml)
        if full:
            profile = {
                "haId": config_entry.unique_id,
                "brand": info.get("brand", ""),
                "vib": info.get("vib", ""),
                "mac": info.get("mac", ""),
                "type": info.get("type", ""),
                "featureMappingFileName": feature_filename,
                "deviceDescriptionFileName": description_filename,
                "connectionType": config_entry.data[CONF_MODE],
                "key": config_entry.data[CONF_PSK],
            }
            if config_entry.data.get(CONF_AES_IV):
                profile["iv"] = config_entry.data[CONF_AES_IV]
            zip_file.writestr(f"{stub}.json", json.dumps(profile, indent=2))

    return buffer.getvalue()
