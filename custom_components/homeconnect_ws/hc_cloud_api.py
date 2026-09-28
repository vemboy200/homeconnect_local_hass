"""
Fetch appliance profiles from the Home Connect cloud API.

Used by the sign-in setup path in config_flow.py as an alternative to uploading
a profile file exported by the Home Connect Profile Downloader tool. The
fetching itself lives in home_disconnect.account; this turns its results into
the same {haId: AppliancePayload} shape process_zip_file produces, so
everything downstream of appliance selection is unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from home_disconnect import AccountError, fetch_profiles
from home_disconnect.account import REGION_ASSET_BASE

if TYPE_CHECKING:
    from aiohttp import ClientSession

    from .const import AppliancePayload

__all__ = ["REGION_ASSET_BASE", "HCCloudApiError", "async_fetch_appliances"]


class HCCloudApiError(Exception):
    """Raised when fetching appliance profiles from the cloud API fails."""


async def async_fetch_appliances(
    session: ClientSession,
    access_token: str,
    region: str,
) -> dict[str, AppliancePayload]:
    """Fetch every paired appliance's profile data, keyed by haId."""
    # Imported here to avoid a circular import (config_flow imports this module).
    from .config_flow import appliance_payload  # noqa: PLC0415

    if region not in REGION_ASSET_BASE:
        msg = f"Invalid region '{region}'"
        raise HCCloudApiError(msg)
    try:
        profiles = await fetch_profiles(session, access_token, region)  # type: ignore[arg-type]
    except AccountError as err:
        raise HCCloudApiError(str(err)) from err
    return {
        loaded.connection.ha_id: appliance_payload(loaded)
        for loaded in profiles
        if loaded.connection is not None
    }
