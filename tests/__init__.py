"""Tests init."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from custom_components.homeconnect_ws.const import DOMAIN
from home_disconnect import Appliance, ConnectionState, parse_profile, serialize_legacy_description
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .const import MOCK_TLS_DEVICE_INFO

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from home_disconnect import DeviceProfile, Program
    from home_disconnect.entities import Entity
    from home_disconnect.messages import Message
    from homeassistant.core import HomeAssistant

type MockApplianceFactory = Callable[..., Awaitable[Appliance]]

_FEATURE_KEYS = (
    "status",
    "setting",
    "event",
    "command",
    "option",
    "program",
    "activeProgram",
    "selectedProgram",
)
_FILLER_STATUS = {"uid": 0x7FFF, "name": "Test.Filler", "access": "read", "available": True}


def mock_session() -> MagicMock:
    """
    Stand in for home_disconnect's Session: connected, and every request succeeds.

    Tests assert on `session.request` to see what was sent. A request's answer is the
    message's own empty response, so `Appliance.connect()` reads no values.
    """
    session = MagicMock()
    session.connected = True
    session.close_code = None
    session.device_info = {}
    session.service_versions = {"ci": 3, "ei": 2, "iz": 1, "ni": 1, "ro": 1}
    session.connect = AsyncMock()
    session.close = AsyncMock()
    session.drop = AsyncMock()

    async def _respond(message: Message) -> Message:
        return message.response()

    session.request = AsyncMock(side_effect=_respond)
    session.send = AsyncMock()
    return session


def profile_from_description(description: Mapping[str, Any]) -> DeviceProfile:
    """
    Parse a test description, written in the stored 1.x dictionary form.

    A profile has to name at least one feature, so a description without any (to test
    what an appliance lacking something gets) gains one unrelated status.
    """
    if not any(description.get(key) for key in _FEATURE_KEYS):
        description = {**description, "status": [_FILLER_STATUS]}
    return parse_profile(*serialize_legacy_description(description))


def make_appliance(description: Mapping[str, Any], **kwargs: Any) -> Appliance:
    """Create a real Appliance for a test description, on a mocked session."""
    kwargs.setdefault("app_name", "mock_app")
    kwargs.setdefault("app_id", "mock_app_id")
    with patch("home_disconnect.appliance.Session", return_value=mock_session()):
        appliance = Appliance(
            MagicMock(),
            "host",
            profile_from_description(description),
            "PSK",
            None,
            info=dict(description.get("info", {})),
            **kwargs,
        )
    # Nothing to read back from a mocked appliance; keeps session.request for writes only.
    appliance._refresh = AsyncMock()  # type: ignore[method-assign]
    return appliance


def appliance_class(appliance: Appliance) -> Mock:
    """
    Stand in for the Appliance class, handing out `appliance`.

    Like the real constructor, it wires up the caller's connection state callback.
    """

    def _create(*_args: Any, on_connection_state: Any = None, **_kwargs: Any) -> Appliance:
        appliance._on_connection_state = on_connection_state
        return appliance

    return Mock(side_effect=_create)


async def update_entity(entity: Entity | Program, data: Mapping[str, Any]) -> None:
    """Apply a value/description change to an entity the way the appliance would."""
    if entity.update(data):
        await entity.run_callbacks()


class MockAppliance:
    """Mock Appliance for config flow."""

    info = MOCK_TLS_DEVICE_INFO

    def __init__(self, info: dict) -> None:
        self.info = info
        self._connect = AsyncMock()
        self._close = AsyncMock()

    def __call__(
        self,
        client_session: Any,
        host: str,
        profile: DeviceProfile,
        psk64: str,
        iv64: str | None = None,
        *,
        app_name: str,
        app_id: str,
        on_connection_state: Callable[[ConnectionState], Awaitable[None]] | None = None,
        **kwargs: Any,
    ) -> Self:
        self.client_session = client_session
        self.host = host
        self.profile = profile
        self.psk64 = psk64
        self.iv64 = iv64
        self.app_name = app_name
        self.app_id = app_id
        self.on_connection_state = on_connection_state
        self.kwargs = kwargs
        return self

    async def _state(self, state: ConnectionState) -> None:
        if self.on_connection_state is not None:
            await self.on_connection_state(state)

    async def connect(self) -> None:
        await self._state(ConnectionState.CONNECTING)
        await self._connect()
        await self._state(ConnectionState.CONNECTED)

    async def close(self) -> None:
        await self._state(ConnectionState.CLOSED)
        await self._close()


async def setup_config_entry(
    hass: HomeAssistant,
    data: dict[str, Any],
    unique_id: str = "any",
) -> bool:
    """Do setup of a MockConfigEntry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=data,
        unique_id=unique_id,
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return result
