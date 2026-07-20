"""HTTP view for downloading an appliance's exported profile ZIP."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from .const import DOMAIN
from .export_profile import build_profile_zip, filename_stub

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class HCExportView(HomeAssistantView):
    """
    Serve a ZIP export of an appliance's profile.

    requires_auth is True deliberately - the full export contains the
    appliance's local encryption key, so this must go through Home
    Assistant's normal session/token authentication like any other page,
    not be reachable by anyone who can guess the URL.
    """

    requires_auth = True
    url = f"/api/{DOMAIN}/export/{{entry_id}}"
    name = f"api:{DOMAIN}:export"

    async def get(self, request: web.Request, entry_id: str) -> web.Response:
        """Return the requested ZIP variant for the given config entry."""
        hass: HomeAssistant = request.app["hass"]
        config_entry = hass.config_entries.async_get_entry(entry_id)
        if config_entry is None or config_entry.domain != DOMAIN:
            return web.Response(status=404, text="Unknown config entry")

        full = request.query.get("mode") != "safe"
        try:
            zip_bytes = await hass.async_add_executor_job(build_profile_zip, config_entry, full)
        except (KeyError, TypeError) as err:
            _LOGGER.exception("Failed to build profile export for %s", entry_id)
            return web.Response(status=500, text=f"Could not build export: {err}")

        suffix = "full" if full else "safe"
        stub = filename_stub(config_entry)
        return web.Response(
            body=zip_bytes,
            content_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{stub}_profile_{suffix}.zip"'},
        )
