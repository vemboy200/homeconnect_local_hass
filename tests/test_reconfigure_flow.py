"""Tests for the reconfigure flow."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from custom_components.homeconnect_ws import HC_KEY, LegacyOAuthCache, async_setup, config_flow
from custom_components.homeconnect_ws.const import (
    CONF_AES_IV,
    CONF_FILE,
    CONF_MANUAL_HOST,
    CONF_PSK,
    DOMAIN,
)
from custom_components.homeconnect_ws.hc_legacy_oauth import LegacyOAuthToken
from home_disconnect import ParserError
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
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
        AsyncMock(
            return_value=LegacyOAuthToken(access_token="fake_token", expires_in=3600)  # noqa: S106
        ),
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

    await async_setup(hass, {})
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

    cache = hass.data[HC_KEY].legacy_oauth_cache
    assert cache is not None
    assert cache.region == "EU"
    assert cache.access_token == "fake_token"  # noqa: S105
    assert cache.expires_at > dt_util.utcnow()


async def test_reconfigure_profile_sign_in_reuses_valid_cache(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    mock_setup_entry: AsyncMock,
) -> None:
    """A still-good cached token skips the whole browser round-trip."""
    appliance = MockAppliance(MOCK_AES_DEVICE_INFO)
    monkeypatch.setattr(config_flow, "HomeAppliance", appliance)
    exchange_mock = AsyncMock()
    monkeypatch.setattr(config_flow, "legacy_async_exchange_code_for_token", exchange_mock)
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

    await async_setup(hass, {})
    hass.data[HC_KEY].legacy_oauth_cache = LegacyOAuthCache(
        region="EU",
        access_token="cached_token",  # noqa: S106
        expires_at=dt_util.utcnow() + timedelta(minutes=30),
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
    await hass.async_block_till_done()

    # No form was shown at all - the cached token took us straight through.
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    exchange_mock.assert_not_awaited()
    mock_setup_entry.assert_awaited_once()


async def test_reconfigure_profile_sign_in_ignores_expired_cache(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An expired cached token doesn't skip the sign-in - the normal form still shows."""
    appliance = MockAppliance(MOCK_AES_DEVICE_INFO)
    monkeypatch.setattr(config_flow, "HomeAppliance", appliance)
    fetch_mock = AsyncMock()
    monkeypatch.setattr(config_flow, "async_fetch_appliances", fetch_mock)

    await async_setup(hass, {})
    hass.data[HC_KEY].legacy_oauth_cache = LegacyOAuthCache(
        region="EU",
        access_token="stale_token",  # noqa: S106
        expires_at=dt_util.utcnow() - timedelta(minutes=1),
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

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "legacy_oauth_region"
    fetch_mock.assert_not_awaited()


async def test_reconfigure_profile_sign_in_clears_rejected_cache(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cached token the Appliance actually rejects falls back to a fresh sign-in, not an error."""
    appliance = MockAppliance(MOCK_AES_DEVICE_INFO)
    monkeypatch.setattr(config_flow, "HomeAppliance", appliance)
    monkeypatch.setattr(
        config_flow, "async_fetch_appliances", AsyncMock(side_effect=RuntimeError("expired"))
    )

    await async_setup(hass, {})
    hass.data[HC_KEY].legacy_oauth_cache = LegacyOAuthCache(
        region="EU",
        access_token="revoked_token",  # noqa: S106
        expires_at=dt_util.utcnow() + timedelta(minutes=30),
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

    # Falls through to the normal region form instead of aborting the flow.
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "legacy_oauth_region"
    assert hass.data[HC_KEY].legacy_oauth_cache is None


async def test_reconfigure_profile_sign_in_unexpected_error(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A genuinely unexpected failure still surfaces a translated error, not "Unknown error".

    The specific (HCLegacyOAuthError, HCCloudApiError) catch only covers
    failures those two libraries themselves raise - anything else (a cloud
    API response shape neither expects, a library bug) used to fall through
    uncaught to HA's generic "Unknown error" screen.
    """
    monkeypatch.setattr(
        config_flow,
        "legacy_async_exchange_code_for_token",
        AsyncMock(
            return_value=LegacyOAuthToken(access_token="fake_token", expires_in=3600)  # noqa: S106
        ),
    )
    monkeypatch.setattr(
        config_flow,
        "async_fetch_appliances",
        AsyncMock(side_effect=RuntimeError("boom")),
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
    state = parse_qs(urlparse(result["description_placeholders"]["authorize_url"]).query)["state"][
        0
    ]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"legacy_redirect_url": f"homeconnectapp://auth?code=fakecode&state={state}"},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "oauth_fetch_failed"
    assert result["description_placeholders"] == {"error": "boom"}


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
