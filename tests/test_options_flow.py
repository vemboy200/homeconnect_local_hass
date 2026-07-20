"""Tests for the export options flow."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

from homeassistant.data_entry_flow import FlowResultType

from . import setup_config_entry
from .const import MOCK_CONFIG_DATA

if TYPE_CHECKING:
    from home_disconnect.testutils import MockAppliance
    from homeassistant.core import HomeAssistant


async def test_options_flow_shows_export_menu(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,  # noqa: ARG001
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """The options flow shows a mode selector on init."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    entry = hass.config_entries.async_entries("homeconnect_ws")[0]

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_flow_export_creates_notification(
    hass: HomeAssistant,
    mock_appliance: MockAppliance,  # noqa: ARG001
    patch_entity_description: None,  # noqa: ARG001
) -> None:
    """Selecting an export mode closes the flow and creates a notification with a link."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)
    entry = hass.config_entries.async_entries("homeconnect_ws")[0]

    result = await hass.config_entries.options.async_init(entry.entry_id)

    with (
        patch(
            "custom_components.homeconnect_ws.config_flow.get_url",
            return_value="http://homeassistant.local:8123",
        ),
        patch("homeassistant.core.ServiceRegistry.async_call", new_callable=AsyncMock) as mock_call,
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"mode": "full"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    mock_call.assert_awaited_once()
    call_args = mock_call.call_args
    assert call_args.args[0] == "persistent_notification"
    assert call_args.args[1] == "create"
    message = call_args.args[2]["message"]
    assert f"/api/homeconnect_ws/export/{entry.entry_id}?mode=full" in message
