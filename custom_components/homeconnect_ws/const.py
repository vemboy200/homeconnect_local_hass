"""Constants."""

from __future__ import annotations

from typing import Any, Final, TypedDict

from homeassistant.const import Platform


class AppliancePayload(TypedDict):
    """A single appliance's key info, profile info and profile XML, keyed by haId elsewhere."""

    info: dict[str, Any]
    description_info: dict[str, Any]
    description_xml: str
    feature_mapping_xml: str


DOMAIN: Final = "homeconnect_ws"
PLATFORMS: Final = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.LIGHT,
    Platform.FAN,
    Platform.UPDATE,
]

CONF_PSK: Final = "psk"
CONF_AES_IV: Final = "aes_iv"
CONF_FILE: Final = "file"
CONF_MANUAL_HOST: Final = "manual_host"
CONF_REGION: Final = "region"
CONF_DEV_SETUP_FROM_DUMP: Final = "setup_from_dump_enabled"
CONF_DEV_OVERRIDE_HOST: Final = "override_host"
CONF_DEV_OVERRIDE_PSK: Final = "override_psk"

# Matches upstream chris-mc1/homeconnect_local_hass's v2 config entry schema
# exactly (same key strings, same storage_dir/{deviceID}/*.xml layout) so a
# future upstream merge doesn't have to reconcile two different
# "v2-equivalent" schemas.
CONF_APPLIANCE_INFO: Final = "appliance_info"
CONF_DESCRIPTION_FILENAME: Final = "description_filename"
CONF_FEATURE_FILENAME: Final = "feature_filename"

# The profile's original XML, kept inline in the config entry.
CONF_DESCRIPTION_XML: Final = "description_xml"
CONF_FEATURE_MAPPING_XML: Final = "feature_mapping_xml"
