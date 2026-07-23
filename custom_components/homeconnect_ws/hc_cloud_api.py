"""
Fetch appliance profiles from the Home Connect cloud API.

Used by the OAuth setup path in config_flow.py as an alternative to uploading
a profile file exported by the Home Connect Profile Downloader tool. Produces
the same {haId: {"info": ..., "description": ...}} shape process_zip_file
does, so everything downstream of appliance selection is unchanged.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import zipfile
from typing import TYPE_CHECKING, Any, cast

from home_disconnect import ParserError, parse_device_description

if TYPE_CHECKING:
    from aiohttp import ClientSession
    from home_disconnect import DeviceDescription

_LOGGER = logging.getLogger(__name__)

REGION_ASSET_BASE = {
    "EU": "https://eu.services.home-connect.com",
    "NA": "https://na.services.home-connect.com",
    "CN": "https://cn.services.home-connect.cn",
}


class HCCloudApiError(Exception):
    """Raised when fetching appliance profiles from the cloud API fails."""


def _account_id_from_token(access_token: str) -> str:
    """Extract the Home Connect account ID (JWT 'sub' claim) from an access token."""
    try:
        payload_b64 = access_token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        account_id = json.loads(base64.urlsafe_b64decode(payload_b64)).get("sub")
    except (IndexError, ValueError) as err:
        msg = "Could not parse account ID from access token"
        raise HCCloudApiError(msg) from err
    if not account_id:
        msg = "No account ID (sub claim) in access token"
        raise HCCloudApiError(msg)
    return str(account_id)


async def async_fetch_appliances(
    session: ClientSession,
    access_token: str,
    region: str,
) -> dict[str, dict[str, dict[str, Any] | DeviceDescription]]:
    """Fetch every paired appliance's profile data, keyed by haId."""
    if region not in REGION_ASSET_BASE:
        msg = f"Invalid region '{region}'"
        raise HCCloudApiError(msg)
    asset_base = REGION_ASSET_BASE[region]
    account_id = _account_id_from_token(access_token)
    auth_headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}

    async with session.get(
        f"{asset_base}/api/account/v2/accounts/{account_id}/paired-appliances",
        headers=auth_headers,
    ) as resp:
        if resp.status == 401:
            msg = f"Unauthorized fetching paired appliances (wrong region '{region}'?)"
            raise HCCloudApiError(msg)
        if resp.status != 200:
            msg = f"Fetching paired appliances failed ({resp.status})"
            raise HCCloudApiError(msg)
        data = await resp.json(content_type=None)

    all_appliances = data.get("appliances", [])
    appliances = [a for a in all_appliances if not a.get("isDemo")]
    if not appliances:
        msg = "No appliances found on this account"
        raise HCCloudApiError(msg)

    results: dict[str, dict[str, Any]] = {}
    for appliance in appliances:
        ha_id: str = appliance.get("haId", "")
        try:
            results[ha_id] = await _async_fetch_one_appliance(
                session, asset_base, auth_headers, appliance
            )
        except HCCloudApiError:
            _LOGGER.warning("Skipping appliance %s, could not fetch its profile", ha_id)

    if not results:
        msg = "Found appliances, but could not fetch any of their profiles"
        raise HCCloudApiError(msg)
    return results


async def _async_fetch_one_appliance(
    session: ClientSession,
    asset_base: str,
    auth_headers: dict[str, str],
    appliance: dict[str, Any],
) -> dict[str, dict[str, Any] | DeviceDescription]:
    ha_id: str = appliance["haId"]

    async with session.get(
        f"{asset_base}/api/appliance/v2/appliances/{ha_id}/encryption-information",
        headers=auth_headers,
    ) as resp:
        if resp.status != 200:
            msg = f"No encryption info for {ha_id} ({resp.status})"
            raise HCCloudApiError(msg)
        enc_data = await resp.json(content_type=None)

    if enc_data.get("tls", {}).get("key"):
        connection_type, key, iv = "TLS", enc_data["tls"]["key"], None
    elif enc_data.get("aes", {}).get("key"):
        connection_type = "AES"
        key = enc_data["aes"]["key"]
        iv = enc_data["aes"].get("iv")
    else:
        msg = f"No usable encryption key for {ha_id}"
        raise HCCloudApiError(msg)

    async with session.get(
        f"{asset_base}/api/iddf/v1/iddf/{ha_id}",
        headers={"Authorization": auth_headers["Authorization"]},
    ) as resp:
        if resp.status != 200:
            msg = f"Device description fetch failed for {ha_id} ({resp.status})"
            raise HCCloudApiError(msg)
        zip_bytes = await resp.read()

    description_xml = b""
    feature_mapping_xml = b""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                if name.endswith("_DeviceDescription.xml"):
                    description_xml = zf.read(name)
                elif name.endswith("_FeatureMapping.xml"):
                    feature_mapping_xml = zf.read(name)
    except zipfile.BadZipFile as err:
        msg = f"Could not parse device description archive for {ha_id}"
        raise HCCloudApiError(msg) from err

    if not description_xml or not feature_mapping_xml:
        msg = f"Device description archive for {ha_id} is missing expected files"
        raise HCCloudApiError(msg)

    try:
        # home_disconnect's parse_device_description() is typed as str | TextIO,
        # but it just forwards to xmltodict.parse(), which also accepts bytes
        # (and does at every other call site in this codebase too).
        description = parse_device_description(
            cast("str", description_xml), cast("str", feature_mapping_xml)
        )
    except ParserError as err:
        msg = f"Could not parse device description for {ha_id}"
        raise HCCloudApiError(msg) from err

    appliance_info = {
        "haId": ha_id,
        "brand": (appliance.get("brand") or "").upper(),
        "vib": appliance.get("vib", ""),
        "mac": appliance.get("mac", ha_id.rsplit("-", maxsplit=1)[-1]),
        "type": appliance.get("haType") or appliance.get("type", ""),
        "connectionType": connection_type,
        "key": key,
    }
    if iv:
        appliance_info["iv"] = iv

    return {"info": appliance_info, "description": description}
