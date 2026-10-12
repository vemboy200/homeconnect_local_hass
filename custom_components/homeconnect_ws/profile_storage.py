"""
Build an appliance's profile from its config entry, and read upstream v2 entries.

Config entries keep the appliance info under CONF_DESCRIPTION["info"] and the
profile as its two original XML files (CONF_DESCRIPTION_XML,
CONF_FEATURE_MAPPING_XML). Entries created by Home Connect Local 1.x instead
hold the whole description as home-disconnect 1.x parsed it; those are turned
back into XML with home_disconnect's serialize_legacy_description() when the
profile is built.

Upstream chris-mc1/homeconnect_local_hass v2 entries keep the XML as files
under storage_dir/{deviceID}/; load_description_files() reads those so the
entry can be converted to the inline shape once.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from home_disconnect import ProfileError, parse_profile, serialize_legacy_description
from homeassistant.const import CONF_DESCRIPTION
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.storage import STORAGE_DIR

from .const import (
    CONF_APPLIANCE_INFO,
    CONF_DESCRIPTION_FILENAME,
    CONF_DESCRIPTION_XML,
    CONF_FEATURE_FILENAME,
    CONF_FEATURE_MAPPING_XML,
    DOMAIN,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from home_disconnect import DeviceProfile
    from homeassistant.core import HomeAssistant

    from . import HCConfigEntry


def profile_xml_from_entry_data(data: Mapping[str, Any]) -> tuple[str, str]:
    """Return a config entry's DeviceDescription and FeatureMapping XML."""
    if CONF_DESCRIPTION_XML in data:
        return data[CONF_DESCRIPTION_XML], data[CONF_FEATURE_MAPPING_XML]
    # Stored by Home Connect Local 1.x: the description as home-disconnect 1.x
    # parsed it, not the XML.
    return serialize_legacy_description(data[CONF_DESCRIPTION])


def profile_from_entry_data(data: Mapping[str, Any]) -> DeviceProfile:
    """Build the appliance's profile from a config entry's data."""
    try:
        return parse_profile(*profile_xml_from_entry_data(data))
    except ProfileError as err:
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="invalid_profile",
            translation_placeholders={"error": str(err)},
        ) from err


def _load_description_files_sync(storage_dir: Path, config_entry: HCConfigEntry) -> dict[str, Any]:
    description_path = storage_dir / config_entry.data[CONF_DESCRIPTION_FILENAME]
    feature_path = storage_dir / config_entry.data[CONF_FEATURE_FILENAME]
    description_xml = description_path.read_text()
    feature_mapping_xml = feature_path.read_text()
    profile = parse_profile(description_xml, feature_mapping_xml)
    # The XML doesn't carry connection-time fields like deviceID - those
    # only ever came from the live appliance, and got stashed separately
    # under CONF_APPLIANCE_INFO for exactly this reason.
    info: dict[str, Any] = {
        "type": profile.info.type,
        "brand": profile.info.brand,
        "model": profile.info.model,
        "vib": profile.info.model,
    }
    info.update(config_entry.data[CONF_APPLIANCE_INFO])
    return {
        CONF_DESCRIPTION: {"info": info},
        CONF_DESCRIPTION_XML: description_xml,
        CONF_FEATURE_MAPPING_XML: feature_mapping_xml,
    }


async def load_description_files(
    hass: HomeAssistant, config_entry: HCConfigEntry
) -> dict[str, Any]:
    """Read a v2-shaped entry's stored XML files into this integration's entry data keys."""
    storage_dir = Path(hass.config.path(STORAGE_DIR, DOMAIN))
    return await hass.async_add_executor_job(
        _load_description_files_sync, storage_dir, config_entry
    )


def _remove_description_files_sync(storage_dir: Path, config_entry: HCConfigEntry) -> None:
    for key in (CONF_DESCRIPTION_FILENAME, CONF_FEATURE_FILENAME):
        with contextlib.suppress(FileNotFoundError):
            (storage_dir / config_entry.data[key]).unlink()
    with contextlib.suppress(FileNotFoundError, OSError):
        (storage_dir / config_entry.data[CONF_DESCRIPTION_FILENAME]).parent.rmdir()


async def remove_description_files(hass: HomeAssistant, config_entry: HCConfigEntry) -> None:
    """Delete a v2 entry's now-unneeded XML files after converting it down to v1."""
    storage_dir = Path(hass.config.path(STORAGE_DIR, DOMAIN))
    await hass.async_add_executor_job(_remove_description_files_sync, storage_dir, config_entry)
