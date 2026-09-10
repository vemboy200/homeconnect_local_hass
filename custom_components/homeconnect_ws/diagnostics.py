"""Diagnostics support."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from home_disconnect import serialize_device_description
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_DESCRIPTION, CONF_DEVICE_ID

from .const import CONF_AES_IV, CONF_PSK

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import HCConfigEntry

TO_REDACT = [CONF_PSK, CONF_AES_IV, CONF_DEVICE_ID, "serialNumber", "deviceID", "shipSki", "mac"]


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,  # noqa: ARG001
    entry: HCConfigEntry,
) -> dict[str, Any]:
    """
    Return diagnostics for a config entry.

    device_description_xml/feature_mapping_xml are the same content the
    options flow's Safe export ZIP has (no key/MAC/serial number, just the
    feature schema) - this is that export's native, one-click equivalent, so
    a single "Download Diagnostics" click covers both what a feature request
    needs (the XML) and what a bug report needs (redacted entry_data plus
    live appliance_state).
    """
    description = entry.data[CONF_DESCRIPTION]
    info = description["info"]
    device_description_xml, feature_mapping_xml = serialize_device_description(description)

    return {
        "brand": info.get("brand"),
        "model": info.get("vib") or info.get("model") or info.get("type"),
        "device_description_xml": device_description_xml,
        "feature_mapping_xml": feature_mapping_xml,
        "entry_data": async_redact_data(entry.data, TO_REDACT),
        "appliance_state": entry.runtime_data.appliance.dump(),
    }
