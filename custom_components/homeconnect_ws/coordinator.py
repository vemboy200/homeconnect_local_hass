"""Home Connect Coordinator."""

from __future__ import annotations

import asyncio
import logging
import time
from copy import deepcopy
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from home_disconnect import (
    Appliance,
    ConnectionState,
    HomeDisconnectError,
)
from home_disconnect.session import RECONNECT_MAX_DELAY
from homeassistant.const import CONF_DESCRIPTION, CONF_DEVICE_ID, CONF_HOST
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_AES_IV,
    CONF_PSK,
    DOMAIN,
)
from .profile_storage import profile_from_entry_data

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import HCConfigEntry

_LOGGER = logging.getLogger(__name__)

# "Can't connect" has several causes (wrong key, appliance offline, a stuck local API), so the
# error links to the troubleshooting page. A test checks the page and heading still exist.
TROUBLESHOOTING_URL = (
    "https://github.com/vemboy200/homeconnect_local_hass/blob/beta"
    "/docs/integration/support-and-troubleshooting.md"
    "#home-assistant-cannot-connect-to-my-appliance-what-should-i-do"
)

# A second quick attempt before failing setup: a reset mid-handshake failed a reachable
# appliance's whole setup (fork issue #9). HA's ConfigEntryNotReady retries take over after.
SETUP_CONNECT_ATTEMPTS = 2
SETUP_CONNECT_RETRY_DELAY = 3  # seconds

# Washers and dryers retry at least this often instead of backing off to 5 minutes, so they're
# picked up soon after they turn their Wi-Fi back on, even where mDNS doesn't work.
LAUNDRY_RECONNECT_MAX_DELAY = 20  # seconds

# Washers and dryers turn their Wi-Fi off when switched off (fork issue #7), so being
# unreachable is normal for them: setup doesn't wait for a connection and failures are only
# logged at debug level. Some washer-dryers stay online and some don't (upstream #426); treating
# them all as laundry is harmless for the ones that stay online.
EXPECTED_OFFLINE_APPLIANCE_TYPES = frozenset({"Washer", "Dryer", "WasherDryer"})

# The Wi-Fi and IP address sensors poll /ni/info on the same timer; polls this close together
# share one request.
NETWORK_INFO_COALESCE_WINDOW = timedelta(seconds=5)


class HomeConnectCoordinator(DataUpdateCoordinator[None]):
    """My custom coordinator."""

    config_entry: HCConfigEntry
    appliance: Appliance
    connected: bool = False
    _escalate_connectivity_logging: bool
    _network_info_lock: asyncio.Lock
    _network_info: list[dict[str, Any]] | None = None
    _network_info_fetched_at: float | None = None

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: HCConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name=config_entry.data["description"]["info"]["vib"],
            config_entry=config_entry,
            always_update=True,
        )
        appliance_info = config_entry.data[CONF_DESCRIPTION].get("info", {})
        if not appliance_info:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="no_device_info",
            )
        self._escalate_connectivity_logging = (
            appliance_info.get("type") not in EXPECTED_OFFLINE_APPLIANCE_TYPES
        )
        self.appliance = Appliance(
            async_get_clientsession(hass),
            config_entry.data[CONF_HOST],
            profile_from_entry_data(config_entry.data),
            config_entry.data[CONF_PSK],
            config_entry.data.get(CONF_AES_IV, None),
            app_name="Homeassistant",
            app_id=config_entry.data[CONF_DEVICE_ID],
            on_connection_state=self._connection_state_callback,
            reconnect_max_delay=(
                RECONNECT_MAX_DELAY
                if self._escalate_connectivity_logging
                else LAUNDRY_RECONNECT_MAX_DELAY
            ),
            info=deepcopy(appliance_info),
        )
        self.disconnect_time = time.time()
        self._network_info_lock = asyncio.Lock()

    @property
    def expected_offline(self) -> bool:
        """
        Whether being disconnected right now is expected, not a fault.

        Only for laundry appliances, and only while disconnected after a clean close (code
        1000) or before any connection since Home Assistant started (fork issue #7). A
        connected appliance hasn't closed either, hence the explicit check (fork issue #21:
        Power stuck at Off on a washer that stays online).
        """
        if self._escalate_connectivity_logging or self.appliance.connected:
            return False
        return self.appliance.closed_cleanly is not False

    async def close(self) -> None:
        await self.appliance.close()

    async def _async_setup(self) -> None:
        if not self._escalate_connectivity_logging:
            # Laundry connects in the background, retrying until it works, so a switched-off
            # washer doesn't stop its entities being created.
            await self.appliance.start()
            return

        self.logger.debug(
            "Connecting to %s", self.config_entry.data[CONF_DESCRIPTION]["info"].get("vib")
        )
        last_err: Exception | None = None
        for attempt in range(SETUP_CONNECT_ATTEMPTS):
            if attempt:
                await asyncio.sleep(SETUP_CONNECT_RETRY_DELAY)
            try:
                await self.appliance.connect()
            except Exception as err:  # noqa: BLE001 - retried, then re-raised below
                await self.appliance.close()
                last_err = err
                continue

            if self.appliance.connected:
                self.connected = True
                self.async_set_updated_data(None)
                return

            await self.appliance.close()

        # UpdateFailed, not ConfigEntryNotReady: from _async_setup the latter logs a traceback
        # on every retry (fork issue #30). The first refresh turns this into ConfigEntryNotReady.
        raise UpdateFailed(
            translation_domain=DOMAIN,
            translation_key=(
                "setup_cannot_connect" if last_err is None else "setup_cannot_connect_error"
            ),
            translation_placeholders={
                "host": self.config_entry.data[CONF_HOST],
                "error": f"{type(last_err).__name__}: {last_err}",
                "url": TROUBLESHOOTING_URL,
            },
        ) from last_err

    def async_nudge_reconnect(self) -> None:
        """
        Retry now; called when the appliance announces itself over mDNS again.

        Does nothing unless the library is waiting to reconnect.

        Sleeping appliances can refuse connections for hours (fork issue #119), so the backoff
        is at 5 minutes by the time they wake and announce themselves.
        """
        self.appliance.retry_now()

    async def async_get_network_info(self) -> list[dict[str, Any]] | None:
        """Get the appliance's /ni/info data, shared by the Wi-Fi and IP address sensors."""
        async with self._network_info_lock:
            now = time.time()
            if (
                self._network_info_fetched_at is not None
                and now - self._network_info_fetched_at
                < NETWORK_INFO_COALESCE_WINDOW.total_seconds()
            ):
                return self._network_info
            if not self.appliance.connected:
                # Laundry entities can poll before the first connection, any entity during a drop.
                self.logger.debug("Network info update skipped: not connected")
                return self._network_info
            try:
                self._network_info = await self.appliance.get_network_info()
            except (HomeDisconnectError, TimeoutError) as err:
                self.logger.debug("Network info update failed: %s", err)
            else:
                self._network_info_fetched_at = now
            return self._network_info

    async def _async_update_data(self) -> None:
        return None

    async def _connection_state_callback(self, event: ConnectionState) -> None:
        if event == ConnectionState.CONNECTED:
            if not self.connected:
                self.logger.info(
                    "Connection to %s restored",
                    self.config_entry.data[CONF_DESCRIPTION]["info"].get("vib"),
                )
            self.connected = True

        elif event in (ConnectionState.RECONNECTING, ConnectionState.DISCONNECTED):
            if self.connected and self._escalate_connectivity_logging:
                self.logger.warning(
                    "Connection to %s lost",
                    self.config_entry.data[CONF_DESCRIPTION]["info"].get("vib"),
                )
            self.connected = False

        elif event == ConnectionState.CLOSED:
            self.connected = False

        self.async_set_updated_data(None)
