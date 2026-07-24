"""HTTP view for downloading an appliance's exported profile ZIP."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiohttp import web
from homeassistant.helpers.http import HomeAssistantView

from .const import DOMAIN
from .export_profile import build_profile_zip, filename_stub

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class HCExportView(HomeAssistantView):
    """
    Serve the Safe ZIP export of an appliance's profile.

    Only ever serves the Safe variant - no key, MAC, or serial number, just
    the feature schema, meant to be shared. The Full export (which contains
    the real local encryption key) is deliberately never served over HTTP,
    not even via a signed link: a link is "possession equals access" and
    would sit in the notification history and HA's own access log for its
    whole validity window. Full export is written straight to the config
    directory instead (see config_flow.py's HCOptionsFlowHandler), which
    requires actual filesystem access to retrieve.

    requires_auth is True regardless, matching every other authenticated
    view - Safe isn't sensitive, but there's no reason to special-case it.
    """

    requires_auth = True
    url = f"/api/{DOMAIN}/export/{{entry_id}}"
    name = f"api:{DOMAIN}:export"

    async def get(self, request: web.Request, entry_id: str) -> web.Response:
        """Return the Safe ZIP export for the given config entry."""
        hass: HomeAssistant = request.app["hass"]
        config_entry = hass.config_entries.async_get_entry(entry_id)
        if config_entry is None or config_entry.domain != DOMAIN:
            return web.Response(status=404, text="Unknown config entry")

        try:
            zip_bytes = await hass.async_add_executor_job(
                build_profile_zip,
                config_entry,
                False,  # noqa: FBT003
            )
        except (KeyError, TypeError) as err:
            _LOGGER.exception("Failed to build profile export for %s", entry_id)
            return web.Response(status=500, text=f"Could not build export: {err}")

        stub = filename_stub(config_entry)
        return web.Response(
            body=zip_bytes,
            content_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{stub}_profile_safe.zip"'},
        )
