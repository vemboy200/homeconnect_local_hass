"""Write a config entry's device profile into HA's storage directory (v2 config entry schema)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from home_disconnect import serialize_device_description
from homeassistant.helpers.storage import STORAGE_DIR

from .const import CONF_DESCRIPTION_FILENAME, CONF_FEATURE_FILENAME, DOMAIN

if TYPE_CHECKING:
    from home_disconnect import DeviceDescription
    from homeassistant.core import HomeAssistant


def _write_description_files_sync(
    storage_dir: Path, device_id: str, description: DeviceDescription
) -> dict[str, str]:
    device_description_xml, feature_mapping_xml = serialize_device_description(description)
    description_filename = f"{device_id}/DeviceDescription.xml"
    feature_filename = f"{device_id}/FeatureMapping.xml"
    for filename, content in (
        (description_filename, device_description_xml),
        (feature_filename, feature_mapping_xml),
    ):
        path = storage_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return {
        CONF_DESCRIPTION_FILENAME: description_filename,
        CONF_FEATURE_FILENAME: feature_filename,
    }


async def write_description_files(
    hass: HomeAssistant, device_id: str, description: DeviceDescription
) -> dict[str, str]:
    """
    Serialize a parsed description back to XML and write it under HA's storage dir.

    Matches upstream chris-mc1/homeconnect_local_hass's v2 config entry
    storage layout exactly (storage_dir/{deviceID}/*.xml) so a future
    upstream merge doesn't have to reconcile two different schemas. Returns
    the CONF_DESCRIPTION_FILENAME/CONF_FEATURE_FILENAME values to store on
    the entry.
    """
    storage_dir = Path(hass.config.path(STORAGE_DIR, DOMAIN))
    return await hass.async_add_executor_job(
        _write_description_files_sync, storage_dir, device_id, description
    )
