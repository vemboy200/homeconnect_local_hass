"""Application credentials platform for Home Connect Local."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.application_credentials import AuthorizationServer

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

# Global auth server regardless of region - matches HA core's own home_connect
# integration (see aiohomeconnect.const), which uses the same endpoint for
# EU/NA/CN accounts. Only the appliance data endpoints differ by region.
OAUTH2_AUTHORIZE = "https://api.home-connect.com/security/oauth/authorize"
OAUTH2_TOKEN = "https://api.home-connect.com/security/oauth/token"  # noqa: S105


async def async_get_authorization_server(hass: HomeAssistant) -> AuthorizationServer:  # noqa: ARG001
    """Return authorization server."""
    return AuthorizationServer(
        authorize_url=OAUTH2_AUTHORIZE,
        token_url=OAUTH2_TOKEN,
    )


async def async_get_description_placeholders(hass: HomeAssistant) -> dict[str, str]:  # noqa: ARG001
    """Return description placeholders for the credentials dialog."""
    return {
        "developer_dashboard_url": "https://developer.home-connect.com/",
        "applications_url": "https://developer.home-connect.com/applications",
        "register_application_url": "https://developer.home-connect.com/application/add",
        "redirect_url": "https://my.home-assistant.io/redirect/oauth",
    }
