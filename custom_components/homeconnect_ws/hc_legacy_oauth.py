"""
Diagnostic-only OAuth path using the Profile Downloader's borrowed credentials.

NOT for real use, not core-compliant, not something that should ship. This
exists solely to answer one question: do the profile-fetch endpoints
(paired-appliances/encryption-information/iddf) work for a normal
self-registered application_credentials app, or only for BSH's own
first-party client (which the bruestel/homeconnect-profile-downloader tool
and PR chris-mc1/homeconnect_local_hass#405 borrow the credentials of)?

Unconditionally visible on this beta branch (simplified-setup) so it doesn't
require editing configuration.yaml just to test - deleted before this reaches
main or a real release. Delete this once the question above is answered.
"""

from __future__ import annotations

import base64
import hashlib
import os
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlencode, urlparse

if TYPE_CHECKING:
    from aiohttp import ClientSession

CLIENT_ID = "9B75AC9EC512F36C84256AC47D813E2C1DD0D6520DF774B020E1E6E2EB29B1F3"
REDIRECT_URI = "hcauth://auth/prod"
# Matches bruestel/homeconnect-profile-downloader's main.js exactly. The borrowed
# client is pre-authorized for the undocumented internal scopes (ReadAccount,
# ReadOrigApi, WriteOrigApi, ...) that paired-appliances/encryption-information/iddf
# actually require - omitting them yields a token with no rights to those endpoints.
SCOPE = (
    "Control DeleteAppliance IdentifyAppliance Images Monitor "
    "ReadAccount ReadOrigApi Settings WriteAppliance WriteOrigApi"
)
REGION_API_BASE = {
    "EU": "https://api.home-connect.com",
    "NA": "https://api-rna.home-connect.com",
    "CN": "https://api.home-connect.cn",
}
URLENCODED = {"Content-Type": "application/x-www-form-urlencoded"}


class HCLegacyOAuthError(Exception):
    """Raised when the diagnostic PKCE handshake fails."""


def generate_code_verifier() -> str:
    """Generate a PKCE code verifier."""
    return base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()


def generate_code_challenge(verifier: str) -> str:
    """Generate a PKCE code challenge from a verifier."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def generate_state() -> str:
    """Generate a random state value."""
    return base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()


def build_authorize_url(region: str, code_verifier: str, state: str) -> str:
    """Build the authorize URL for the user to open in their own browser."""
    if region not in REGION_API_BASE:
        msg = f"Invalid region '{region}'"
        raise HCLegacyOAuthError(msg)
    params = {
        "redirect_url": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "response_type": "code",
        "prompt": "login",
        "code_challenge_method": "S256",
        "code_challenge": generate_code_challenge(code_verifier),
        "state": state,
        "nonce": generate_state(),
        "scope": SCOPE,
    }
    return f"{REGION_API_BASE[region]}/security/oauth/authorize?{urlencode(params)}"


def extract_code_from_redirect(redirect_url: str, expected_state: str) -> str:
    """Extract the authorization code from the (dead) redirect URL the user pastes back."""
    try:
        parsed = urlparse(redirect_url)
        params = parse_qs(parsed.query) or parse_qs(parsed.fragment)
    except ValueError as err:
        msg = "Could not parse the pasted URL"
        raise HCLegacyOAuthError(msg) from err
    if "code" not in params:
        msg = "No authorization code found in the pasted URL"
        raise HCLegacyOAuthError(msg)
    if params.get("state", [None])[0] != expected_state:
        msg = "State mismatch - please restart this diagnostic flow"
        raise HCLegacyOAuthError(msg)
    return params["code"][0]


async def async_exchange_code_for_token(
    session: ClientSession, region: str, code: str, code_verifier: str
) -> str:
    """Exchange an authorization code for an access token."""
    async with session.post(
        f"{REGION_API_BASE[region]}/security/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code_verifier": code_verifier,
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
        headers=URLENCODED,
    ) as resp:
        data = await resp.json(content_type=None)
        if resp.status != 200:
            msg = f"Token request failed ({resp.status}): {data}"
            raise HCLegacyOAuthError(msg)
        token = data.get("access_token")
        if not token:
            msg = f"No access_token in response: {data}"
            raise HCLegacyOAuthError(msg)
        return token
