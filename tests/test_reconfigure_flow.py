"""Tests for the reconfigure flow."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from custom_components.homeconnect_ws import config_flow
from custom_components.homeconnect_ws.const import (
    CONF_AES_IV,
    CONF_FILE,
    CONF_MANUAL_HOST,
    CONF_PSK,
    DOMAIN,
)
from home_disconnect import ParserError
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from . import MockAppliance
from .const import (
    MOCK_AES_DEVICE_DESCRIPTION,
    MOCK_AES_DEVICE_ID,
    MOCK_AES_DEVICE_INFO,
    MOCK_CONFIG_DATA,
)

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    import pytest
    from homeassistant.core import HomeAssistant

UPLOADED_FILE = str(uuid4())
AUTO_HOST = "Fake_deviceID"  # MOCK_APPLIANCE_INFO["deviceID"], AES mode uses it as-is


def _mock_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG_DATA,
        unique_id=MOCK_AES_DEVICE_ID,
    )


async def test_reconfigure_menu(hass: HomeAssistant) -> None:
    """Test the reconfigure flow shows a menu with both options."""
    mock_config = _mock_entry()
    mock_config.add_to_hass(hass)

    result = await mock_config.start_reconfigure_flow(hass)

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "reconfigure"
    assert set(result["menu_options"]) == {"reconfigure_connection", "reconfigure_profile"}


async def test_reconfigure_connection_auto_succeeds(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test that picking Change Connection tries automatic discovery first."""
    appliance = MockAppliance(MOCK_AES_DEVICE_INFO)
    monkeypatch.setattr(config_flow, "HomeAppliance", appliance)

    mock_config = _mock_entry()
    mock_config.add_to_hass(hass)

    result = await mock_config.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "reconfigure_connection"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config.data[CONF_MANUAL_HOST] is False
    assert mock_config.data[CONF_HOST] == AUTO_HOST
    # The rest of the entry (description, keys) is untouched.
    assert mock_config.data[CONF_PSK] == MOCK_CONFIG_DATA[CONF_PSK]

    appliance._connect.assert_awaited_once()
    appliance._close.assert_awaited_once()
    mock_setup_entry.assert_awaited_once()


async def test_reconfigure_connection_falls_back_to_manual_host(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test that a failed automatic attempt falls back to asking for a fixed IP."""
    appliance = MockAppliance(MOCK_AES_DEVICE_INFO)
    monkeypatch.setattr(config_flow, "HomeAppliance", appliance)
    appliance._connect.side_effect = [TimeoutError(), None]

    mock_config = _mock_entry()
    mock_config.add_to_hass(hass)

    result = await mock_config.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "reconfigure_connection"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "host"
    assert result["errors"]["base"] == "cannot_connect_automatic"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_HOST: "10.0.0.5"},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config.data[CONF_MANUAL_HOST] is True
    assert mock_config.data[CONF_HOST] == "10.0.0.5"

    mock_setup_entry.assert_awaited_once()


async def test_reconfigure_connection_failed(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test both the automatic attempt and the manual retry failing."""
    appliance = MockAppliance(MOCK_AES_DEVICE_INFO)
    monkeypatch.setattr(config_flow, "HomeAppliance", appliance)
    appliance._connect.side_effect = TimeoutError()

    mock_config = _mock_entry()
    mock_config.add_to_hass(hass)

    result = await mock_config.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "reconfigure_connection"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_HOST: "10.0.0.5"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "host"
    assert result["errors"]["base"] == "cannot_connect"

    hass.config_entries.flow.async_abort(result["flow_id"])
    mock_setup_entry.assert_not_awaited()


async def test_reconfigure_profile_via_upload(
    hass: HomeAssistant,
    mock_process_profile_file: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test refreshing the profile via a fresh file upload."""
    appliance = MockAppliance(MOCK_AES_DEVICE_INFO)
    monkeypatch.setattr(config_flow, "HomeAppliance", appliance)

    mock_process_profile_file.return_value[MOCK_AES_DEVICE_ID]["info"]["key"] = "New_AES_PSK_KEY"
    mock_process_profile_file.return_value[MOCK_AES_DEVICE_ID]["info"]["iv"] = "New_AES_IV"

    mock_config = _mock_entry()
    mock_config.add_to_hass(hass)

    result = await mock_config.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "reconfigure_profile"}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "reconfigure_profile"
    assert set(result["menu_options"]) == {"legacy_oauth_region", "upload"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "upload"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "upload"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_FILE: UPLOADED_FILE},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config.data[CONF_PSK] == "New_AES_PSK_KEY"
    assert mock_config.data[CONF_AES_IV] == "New_AES_IV"
    # Host is untouched by a profile refresh.
    assert mock_config.data[CONF_HOST] == MOCK_CONFIG_DATA[CONF_HOST]

    mock_setup_entry.assert_awaited_once()


async def test_reconfigure_profile_via_sign_in(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test refreshing the profile via a fresh Home Connect sign-in instead of a file."""
    appliance = MockAppliance(MOCK_AES_DEVICE_INFO)
    monkeypatch.setattr(config_flow, "HomeAppliance", appliance)
    monkeypatch.setattr(
        config_flow,
        "legacy_async_exchange_code_for_token",
        AsyncMock(return_value="fake_token"),
    )
    monkeypatch.setattr(
        config_flow,
        "async_fetch_appliances",
        AsyncMock(
            return_value={
                MOCK_AES_DEVICE_ID: {
                    "info": MOCK_AES_DEVICE_INFO,
                    "description": MOCK_AES_DEVICE_DESCRIPTION,
                }
            }
        ),
    )

    mock_config = _mock_entry()
    mock_config.add_to_hass(hass)

    result = await mock_config.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "reconfigure_profile"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "legacy_oauth_region"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"region": "EU"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "legacy_oauth_paste"

    state = parse_qs(urlparse(result["description_placeholders"]["authorize_url"]).query)["state"][
        0
    ]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"legacy_redirect_url": f"homeconnectapp://auth?code=fakecode&state={state}"},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    mock_setup_entry.assert_awaited_once()


async def test_reconfigure_profile_appliance_not_in_file(
    hass: HomeAssistant,
    mock_process_profile_file: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test uploading a profile file for a different Appliance aborts."""
    mock_config = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG_DATA,
        unique_id="other_id",
    )
    mock_config.add_to_hass(hass)

    result = await mock_config.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "reconfigure_profile"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "upload"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_FILE: UPLOADED_FILE},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "appliance_not_in_profile_file"
    mock_setup_entry.assert_not_awaited()


async def test_reconfigure_profile_invalid_config_parser(
    hass: HomeAssistant,
    mock_process_profile_file: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test a reconfigure profile upload with error in config parser."""
    mock_config = _mock_entry()
    mock_config.add_to_hass(hass)

    mock_process_profile_file.side_effect = ParserError("Test Error")

    result = await mock_config.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "reconfigure_profile"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "upload"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_FILE: UPLOADED_FILE},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "profile_file_parser_error"
    assert result["description_placeholders"] == {"error": "Test Error"}
    mock_setup_entry.assert_not_awaited()
