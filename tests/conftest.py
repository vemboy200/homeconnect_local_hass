"""Fixtures for testing."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from zipfile import ZipFile

import pytest
from custom_components import homeconnect_ws
from custom_components.homeconnect_ws import coordinator, entity_descriptions

from . import MockApplianceFactory, appliance_class, make_appliance

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from home_disconnect import Appliance

from .const import (
    DEVICE_DESCRIPTION,
    ENTITY_DESCRIPTIONS,
    MOCK_AES_DESCRIPTION_XML,
    MOCK_AES_DEVICE_ID,
    MOCK_AES_DEVICE_INFO,
    MOCK_AES_FEATURE_MAPPING_XML,
    MOCK_AES_PAYLOAD,
    MOCK_TLS_DESCRIPTION_XML,
    MOCK_TLS_DEVICE_ID,
    MOCK_TLS_DEVICE_ID_2,
    MOCK_TLS_DEVICE_INFO,
    MOCK_TLS_FEATURE_MAPPING_XML,
    MOCK_TLS_PAYLOAD,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations defined in the test dir."""
    return


@pytest.fixture
def patch_entity_description(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch entity_description for testing."""
    monkeypatch.setattr(
        entity_descriptions, "get_available_entities", Mock(return_value=ENTITY_DESCRIPTIONS)
    )
    monkeypatch.setattr(
        homeconnect_ws, "get_available_entities", Mock(return_value=ENTITY_DESCRIPTIONS)
    )


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        "custom_components.homeconnect_ws.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.fixture
def create_profile_file(tmp_path: Path) -> Path:
    """Create a test profile file."""
    file_path = tmp_path / "TestProfileFile.zip"

    with ZipFile(file_path, mode="w") as file:
        # TLS Appliance
        file.writestr("010203040506070809_FeatureMapping.xml", MOCK_TLS_FEATURE_MAPPING_XML)
        file.writestr("010203040506070809_DeviceDescription.xml", MOCK_TLS_DESCRIPTION_XML)
        file.writestr("010203040506070809.json", json.dumps(MOCK_TLS_DEVICE_INFO))
        # AES Appliance
        file.writestr("101112131415161718_FeatureMapping.xml", MOCK_AES_FEATURE_MAPPING_XML)
        file.writestr("101112131415161718_DeviceDescription.xml", MOCK_AES_DESCRIPTION_XML)
        file.writestr("101112131415161718.json", json.dumps(MOCK_AES_DEVICE_INFO))
    return file_path


@pytest.fixture
def mock_process_uploaded_file(
    create_profile_file: Path,
) -> Generator[MagicMock]:
    """Mock upload profile files."""
    ctx_mock = MagicMock()
    ctx_mock.__enter__.return_value = create_profile_file
    with patch(
        "custom_components.homeconnect_ws.config_flow.process_uploaded_file",
        return_value=ctx_mock,
    ) as mock_upload:
        yield mock_upload


@pytest.fixture
def mock_process_profile_file() -> Generator[MagicMock]:
    """Mock process profile files."""
    device_description = {
        MOCK_TLS_DEVICE_ID: MOCK_TLS_PAYLOAD,
        MOCK_AES_DEVICE_ID: MOCK_AES_PAYLOAD,
        MOCK_TLS_DEVICE_ID_2: MOCK_TLS_PAYLOAD,
    }
    with patch(
        "custom_components.homeconnect_ws.config_flow.HomeConnectConfigFlow._process_profile_file",
        return_value=deepcopy(device_description),
    ) as mock_upload:
        yield mock_upload


@pytest.fixture
def mock_appliance(monkeypatch: pytest.MonkeyPatch) -> Appliance:
    """Mock the coordinator's Appliance: a real one on a mocked session."""
    appliance = make_appliance(DEVICE_DESCRIPTION)
    monkeypatch.setattr(coordinator, "Appliance", appliance_class(appliance))
    return appliance


@pytest.fixture
def mock_homeconnect_appliance() -> MockApplianceFactory:
    """Create Appliances for test descriptions, on mocked sessions."""

    async def go(description: dict | None = None, **kwargs: Any) -> Appliance:
        return make_appliance(description or {}, **kwargs)

    return go
