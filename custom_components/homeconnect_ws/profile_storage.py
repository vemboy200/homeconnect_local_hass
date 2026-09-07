"""
Read a v2-shaped config entry's device profile out of HA's storage directory.

This fork intentionally keeps its own config entries in the older, simpler
"whole parsed description inline" shape (CONF_DESCRIPTION) rather than
adopting upstream chris-mc1/homeconnect_local_hass's newer v2 schema
(CONF_APPLIANCE_INFO + XML files under storage_dir/{deviceID}/) - this module
exists only so a user switching to this fork with an existing v2 entry (e.g.
created by upstream, or a previous run of this fork's own now-removed v1->v2
migration) gets it converted back down to CONF_DESCRIPTION shape on setup,
instead of the fork having to understand two schemas forever.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING

from home_disconnect import parse_device_description
from homeassistant.helpers.storage import STORAGE_DIR

from .const import CONF_APPLIANCE_INFO, CONF_DESCRIPTION_FILENAME, CONF_FEATURE_FILENAME, DOMAIN

if TYPE_CHECKING:
    from home_disconnect import DeviceDescription
    from homeassistant.core import HomeAssistant

    from . import HCConfigEntry


def _load_description_files_sync(
    storage_dir: Path, config_entry: HCConfigEntry
) -> DeviceDescription:
    description_path = storage_dir / config_entry.data[CONF_DESCRIPTION_FILENAME]
    feature_path = storage_dir / config_entry.data[CONF_FEATURE_FILENAME]
    description = parse_device_description(description_path.read_text(), feature_path.read_text())
    # The static XML doesn't carry connection-time fields like deviceID -
    # those only ever came from the live appliance, and got stashed
    # separately under CONF_APPLIANCE_INFO for exactly this reason.
    description["info"].update(config_entry.data[CONF_APPLIANCE_INFO])
    return description


async def load_description_files(
    hass: HomeAssistant, config_entry: HCConfigEntry
) -> DeviceDescription:
    """Reconstruct a full description from a v2-shaped entry's stored XML files."""
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
