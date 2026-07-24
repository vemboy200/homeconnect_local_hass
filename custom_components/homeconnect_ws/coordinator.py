"""Home Connect Coordinator."""

from __future__ import annotations

import asyncio
import logging
import time
from copy import deepcopy
from datetime import timedelta
from typing import TYPE_CHECKING

import aiohttp
from home_disconnect import (
    AllreadyConnectedError,
    ConnectionFailedError,
    ConnectionState,
    HCHandshakeError,
    HomeAppliance,
)
from homeassistant.const import CONF_DESCRIPTION, CONF_DEVICE_ID, CONF_HOST
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_AES_IV,
    CONF_PSK,
    DOMAIN,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from homeassistant.core import HomeAssistant

    from . import HCConfigEntry

_LOGGER = logging.getLogger(__name__)

CONNECT_RETRY_INITIAL_DELAY = 5  # seconds
CONNECT_RETRY_MAX_DELAY = 60  # seconds

# Standalone washers/dryers disable home-disconnect's own auto-reconnect (see
# reconect=False below) - this is the fallback that takes its place. Fixed,
# not exponential: unlike a connect failure at startup, we have no evidence
# a temporarily-offline laundry appliance takes long to come back once it
# does, and this is the guaranteed path (works even on networks where mDNS
# doesn't route multicast) - an mDNS-triggered immediate reconnect is a
# planned follow-up to shortcut this wait when discovery does work.
LAUNDRY_RECONNECT_POLL_INTERVAL = timedelta(seconds=20)

# Standalone washers and dryers routinely cut their own WiFi radio entirely
# when powered off between cycles (confirmed via fork issue #7 - a clean
# WebSocket close code 1000 followed by the device dropping off the LAN
# entirely, not just closing the local API). Being unreachable is a normal,
# expected state for these, not a fault: setup doesn't block on a successful
# connection, and connect failures don't get escalated past debug-level
# logging (see also upstream chris-mc1/homeconnect_local_hass issues #274 and
# #293). Washer/dryer *combo* units are deliberately excluded here - the one
# combo model checked (WNC254A0BY) stayed connected over Wi-Fi while powered
# off instead, closer to the dishwasher pattern, so combos get the same
# test-before-setup treatment as every other appliance type until there's
# evidence a given combo actually needs the exemption too.
EXPECTED_OFFLINE_APPLIANCE_TYPES = frozenset({"Washer", "Dryer"})


class HomeConnectCoordinator(DataUpdateCoordinator[None]):
    """My custom coordinator."""

    config_entry: HCConfigEntry
    appliance: HomeAppliance
    _connecting: bool = True
    connected: bool = False
    _escalate_connectivity_logging: bool
    _poll_unsub: Callable[[], None] | None = None

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
        self.appliance = HomeAppliance(
            description=deepcopy(config_entry.data[CONF_DESCRIPTION]),
            host=config_entry.data[CONF_HOST],
            app_name="Homeassistant",
            app_id=config_entry.data[CONF_DEVICE_ID],
            psk64=config_entry.data[CONF_PSK],
            iv64=config_entry.data.get(CONF_AES_IV, None),
            session=async_get_clientsession(hass),
            connection_callback=self._connection_state_callback,
            # Standalone washers/dryers get their own fallback-poll-based
            # reconnect (see LAUNDRY_RECONNECT_POLL_INTERVAL) instead of
            # home-disconnect's built-in one, so the two don't hammer the
            # appliance in parallel once the poll and the mDNS-triggered
            # reconnect (a planned follow-up) both exist.
            reconect=self._escalate_connectivity_logging,
        )
        self.disconnect_time = time.time()

    @property
    def expected_offline(self) -> bool:
        """
        Whether being disconnected right now is expected, not a fault.

        True only for appliance types confirmed to legitimately cut their own
        WiFi (EXPECTED_OFFLINE_APPLIANCE_TYPES) AND only when the *most
        recent* disconnect was a clean code-1000 closure. An unexpected drop
        - any other close code, or None if the appliance was never seen
        sending one - still correctly reports as not expected, even for an
        otherwise-exempt appliance type. Matches ESPHome's has_deep_sleep +
        expected_disconnect pattern for its own sleepy-device entities.
        """
        return (
            not self._escalate_connectivity_logging
            and self.appliance.session.last_close_code == 1000
        )

    async def close(self) -> None:
        self._connecting = False
        if self._poll_unsub is not None:
            self._poll_unsub()
            self._poll_unsub = None
        await self.appliance.close()

    async def _async_setup(self) -> None:
        if not self._escalate_connectivity_logging:
            # Standalone washer/dryer: connect in the background, non-blocking.
            # Being unreachable at setup is expected for these (see
            # EXPECTED_OFFLINE_APPLIANCE_TYPES), so we don't want a temporarily
            # powered-off appliance to prevent its entities from being created
            # at all.
            self.config_entry.async_create_task(self.hass, self._connect())
            # _connect() above only covers the *first* connection - it returns
            # for good once that succeeds. reconect=False (see __init__) means
            # home-disconnect won't auto-reconnect after a *later* drop either,
            # so this poll is what actually notices the appliance coming back.
            self._poll_unsub = async_track_time_interval(
                self.hass, self._async_poll_reconnect, LAUNDRY_RECONNECT_POLL_INTERVAL
            )
            return

        self.logger.debug(
            "Connecting to %s", self.config_entry.data[CONF_DESCRIPTION]["info"].get("vib")
        )
        try:
            await self.appliance.connect()
        except Exception as err:
            await self.appliance.close()
            msg = f"Can't connect to {self.config_entry.data[CONF_HOST]}"
            raise ConfigEntryNotReady(msg) from err

        if not self.appliance.session.connected:
            await self.appliance.close()
            msg = f"Can't connect to {self.config_entry.data[CONF_HOST]}"
            raise ConfigEntryNotReady(msg)

        self.connected = True
        self.async_set_updated_data(None)

    async def _connect(self) -> None:
        self.logger.debug(
            "Connecting to %s", self.config_entry.data[CONF_DESCRIPTION]["info"].get("vib")
        )
        first_failure = True
        retry_delay = CONNECT_RETRY_INITIAL_DELAY
        while self._connecting:
            try:
                await self.appliance.connect()
                if self.appliance.session.connected:
                    self.connected = True  # FIX
                    self.async_set_updated_data(None)  # FIX
                    return
            except (ConnectionFailedError, HCHandshakeError, aiohttp.ClientResponseError):
                # aiohttp.ClientResponseError (e.g. a 404 on the websocket upgrade)
                # isn't wrapped by the library into ConnectionFailedError/
                # HCHandshakeError, and doesn't trigger a connection state change
                # either, so it needs to be handled here directly.
                await self.appliance.close()
                self.connected = False
                msg = f"Can't connect to {self.config_entry.data[CONF_HOST]}, retrying"
                if first_failure and self._escalate_connectivity_logging:
                    self.logger.error(msg)  # noqa: TRY400
                    first_failure = False  # first_failure_fix
                else:
                    self.logger.debug(msg)
            except AllreadyConnectedError:
                await self.appliance.close()
                msg = f"Allready connected to {self.config_entry.data[CONF_HOST]}"
                self.logger.error(msg)  # noqa: TRY400
                return
            except Exception:
                await self.appliance.close()
                msg = f"Can't connect to {self.config_entry.data[CONF_HOST]}"
                self.logger.exception(msg)

            if not self._connecting:
                # mypy can't see that close() (a different method) may have
                # flipped this flag while we were suspended on an await above.
                return  # type: ignore[unreachable]
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, CONNECT_RETRY_MAX_DELAY)

    async def _async_poll_reconnect(self, _now: datetime) -> None:
        """
        Fallback reconnect for standalone washers/dryers (reconect=False).

        Runs unconditionally, regardless of mDNS: it's the guaranteed path,
        not a backstop for a separate mDNS-driven reconnect (that's a planned
        follow-up, layered on top of this rather than replacing it).
        """
        if self.connected:
            return
        try:
            await self.appliance.connect()
        except (
            ConnectionFailedError,
            HCHandshakeError,
            aiohttp.ClientResponseError,
            AllreadyConnectedError,
        ):
            self.logger.debug(
                "Reconnect poll: still can't reach %s", self.config_entry.data[CONF_HOST]
            )
            await self.appliance.close()
        except Exception:
            self.logger.exception(
                "Reconnect poll: unexpected error connecting to %s",
                self.config_entry.data[CONF_HOST],
            )
            await self.appliance.close()
        else:
            if self.appliance.session.connected:
                self.connected = True
                self.async_set_updated_data(None)
            else:
                await self.appliance.close()

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

        elif event in (ConnectionState.RECONNECTING, ConnectionState.ABNORMAL_CLOSURE):
            # ABNORMAL_CLOSURE covers a connection that has never succeeded yet
            # (e.g. the appliance is already unreachable when HA starts), since
            # the library only enters RECONNECTING after a prior successful
            # connection drops.
            if self.connected and self._escalate_connectivity_logging:
                self.logger.warning(
                    "Connection to %s lost",
                    self.config_entry.data[CONF_DESCRIPTION]["info"].get("vib"),
                )
            self.connected = False

        elif event == ConnectionState.CLOSED:
            self.connected = False

        self.async_set_updated_data(None)
