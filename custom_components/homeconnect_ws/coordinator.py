"""Home Connect Coordinator."""

from __future__ import annotations

import asyncio
import logging
import time
from copy import deepcopy
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import aiohttp
from aiohttp.client_exceptions import ClientConnectionResetError
from home_disconnect import (
    AllreadyConnectedError,
    ConnectionFailedError,
    ConnectionState,
    HCHandshakeError,
    HomeAppliance,
    NotConnectedError,
)
from homeassistant.const import CONF_DESCRIPTION, CONF_DEVICE_ID, CONF_HOST
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

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

# A sustained "Can't connect" failure has more than one real cause (a stale/
# wrong encryption key, a genuinely offline appliance, or a stuck local API
# needing a power cycle - see the README's "websocket shutdown" section) -
# not something a single log line can diagnose, so point at the doc instead
# of guessing which one it is.
TROUBLESHOOTING_URL = (
    "https://github.com/vemboy200/homeconnect_local_hass"
    "#home-assistant-cannot-connect-to-my-appliance-what-should-i-do"
)

CONNECT_RETRY_INITIAL_DELAY = 5  # seconds
CONNECT_RETRY_MAX_DELAY = 60  # seconds

# Non-exempt appliance types block setup on a single successful connection
# (see test-before-setup in quality_scale.yaml), but a bare single attempt
# turned out to be too fragile: a momentary connection hiccup (e.g. a
# ConnectionResetError mid-handshake, confirmed live on fork issue #9 for a
# WasherDryer combo that was otherwise fully reachable) failed the whole
# config entry instead of just that one attempt, something 1.6.0's always-
# retrying background setup never did for any appliance type. A couple of
# quick attempts smooths over that class of blip without meaningfully
# delaying the case where the appliance really is unreachable - HA's own
# ConfigEntryNotReady backoff still takes over after this gives up.
SETUP_CONNECT_ATTEMPTS = 2
SETUP_CONNECT_RETRY_DELAY = 3  # seconds

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
# #293). Washer/dryer *combo* behavior isn't consistent across models - one
# checked (WNC254A0BY) stayed connected over Wi-Fi while powered off, closer
# to the dishwasher pattern, but upstream issue #426 confirms a different
# combo (WDU28512) does drop off the network like a standalone unit. Included
# here since the exemption is safe either way: an appliance that actually
# stays connected essentially never triggers the lenient path, while one that
# doesn't is spared a false setup error - the only real difference either way
# is whether an occasional unreachable moment gets treated as expected or
# escalated as a fault.
EXPECTED_OFFLINE_APPLIANCE_TYPES = frozenset({"Washer", "Dryer", "WasherDryer"})

# HCWiFI, and the ipv4/ipv6 address sensors, are all should_poll entities on
# the same SCAN_INTERVAL (see sensor.py) and would otherwise each fire their
# own /ni/info request every time that timer elapses - three round trips to
# the appliance for what's the same data every time. A poll landing within
# this window of the last one just reuses that result instead of issuing a
# new request; small relative to the hourly interval, so it only collapses
# near-simultaneous callers, not a legitimate next cycle's fetch.
NETWORK_INFO_COALESCE_WINDOW = timedelta(seconds=5)


class HomeConnectCoordinator(DataUpdateCoordinator[None]):
    """My custom coordinator."""

    config_entry: HCConfigEntry
    appliance: HomeAppliance
    _connecting: bool = True
    connected: bool = False
    _escalate_connectivity_logging: bool
    _poll_unsub: Callable[[], None] | None = None
    # Laundry appliances have three independent triggers that can each call
    # appliance.connect() (the initial _connect() loop, the fallback poll, and
    # the mDNS nudge) - without this, two overlapping attempts would race:
    # the second one raises AllreadyConnectedError, whose handler closes the
    # shared session, tearing down the first attempt's in-progress connection
    # too. Serializes them so at most one is ever actually in flight.
    _connect_lock: asyncio.Lock
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
        self._connect_lock = asyncio.Lock()
        self._network_info_lock = asyncio.Lock()

    @property
    def expected_offline(self) -> bool:
        """
        Whether being disconnected right now is expected, not a fault.

        True only while actually disconnected, for appliance types confirmed
        to legitimately cut their own WiFi (EXPECTED_OFFLINE_APPLIANCE_TYPES),
        unless the *most recent* close code is positively known to be
        something other than a clean code-1000 closure. No close code
        observed yet at all (None) also counts as expected here, not just
        1000 - a fresh HA restart rebuilds the session from scratch, wiping
        last_close_code back to None before this process has ever connected,
        which otherwise made every entity show Unavailable on restart
        whenever the appliance simply happened to be off (confirmed live on
        fork issue #7). These appliance types are already treated as
        "unreachable is normal" everywhere else (no setup blocking,
        debug-only connect-failure logging), so a restart shouldn't be the
        one place that starts them out looking broken.

        The explicit `not session.connected` check matters: home_disconnect
        resets last_close_code back to None the moment a new connection
        succeeds (so a stale code from a past disconnect doesn't linger), but
        that means last_close_code alone can't distinguish "actually
        offline, and it's expected" from "fully connected right now" - both
        show up as None. Without this check, force_off_when_expected_offline/
        force_option_when_expected_offline/clear_on_expected_offline (switch,
        select, sensor, number) would force their placeholder value
        constantly, even while connected and receiving live updates -
        confirmed live on fork issue #21 (Power switch/PowerState sensor
        stuck at Off on an always-online washer).
        """
        if self._escalate_connectivity_logging:
            return False
        if self.appliance.session.connected:
            return False
        return self.appliance.session.last_close_code in {None, 1000}

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
            # at all. async_create_task() would still be tracked and waited on
            # by HA's own startup sequencing, which defeats the point - a
            # washer that's been off since before HA started could keep
            # _connect() retrying for a long time, blocking the rest of HA's
            # bootstrap for minutes (confirmed live on fork issue #16).
            # async_create_background_task() is explicitly documented not to
            # block startup or be waited on by async_block_till_done().
            self.config_entry.async_create_background_task(
                self.hass, self._connect(), "homeconnect_ws laundry connect"
            )
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
        last_err: Exception | None = None
        for attempt in range(SETUP_CONNECT_ATTEMPTS):
            if attempt:
                # A momentary connection hiccup (e.g. a reset mid-handshake)
                # shouldn't fail the whole config entry by itself - give the
                # appliance one more quick chance before falling back to HA's
                # own, much slower, ConfigEntryNotReady retry loop.
                await asyncio.sleep(SETUP_CONNECT_RETRY_DELAY)
            try:
                await self.appliance.connect()
            except Exception as err:  # noqa: BLE001 - retried, then re-raised below
                await self.appliance.close()
                last_err = err
                continue

            if self.appliance.session.connected:
                self.connected = True
                self.async_set_updated_data(None)
                return

            await self.appliance.close()

        msg = f"Can't connect to {self.config_entry.data[CONF_HOST]}"
        if last_err is not None:
            msg += f" ({type(last_err).__name__}: {last_err})"
        msg += f" - see {TROUBLESHOOTING_URL} if this doesn't resolve on its own"
        # UpdateFailed, not ConfigEntryNotReady: HA's own
        # async_config_entry_first_refresh() already converts a failed setup
        # into ConfigEntryNotReady for us. Raising ConfigEntryNotReady
        # ourselves from inside _async_setup doesn't get treated as an
        # expected setup failure by __wrap_async_setup (it isn't a
        # ConfigEntryError subclass) - it falls into the generic except
        # Exception branch instead, which logs a full ERROR-level traceback
        # via "Unexpected error fetching %s data" on *every single retry*
        # while the appliance stays unreachable, before HA discards it and
        # raises its own ConfigEntryNotReady anyway. Confirmed live on fork
        # issue #30 (an oven unreachable for an extended period produced
        # dozens of these). UpdateFailed is handled quietly and still ends
        # up as ConfigEntryNotReady with this as __cause__.
        raise UpdateFailed(msg) from last_err

    async def _connect(self) -> None:
        self.logger.debug(
            "Connecting to %s", self.config_entry.data[CONF_DESCRIPTION]["info"].get("vib")
        )
        first_failure = True
        retry_delay = CONNECT_RETRY_INITIAL_DELAY
        while self._connecting:
            async with self._connect_lock:
                if self.connected:
                    # Another caller (poll/nudge) already connected while we
                    # were waiting for the lock.
                    return
                try:
                    await self.appliance.connect()
                    if self.appliance.session.connected:
                        self.connected = True
                        self.async_set_updated_data(None)
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
                    # Shouldn't happen now that _connect_lock serializes every
                    # caller - kept as a defensive fallback, not the expected path.
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
        async with self._connect_lock:
            # Re-check: _connect()'s own loop, or an earlier poll/nudge
            # invocation, may have already connected while we waited for
            # the lock - mypy can't see that awaiting the lock above is a
            # suspension point where that can happen.
            if self.connected:
                return  # type: ignore[unreachable]
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

    def async_nudge_reconnect(self) -> None:
        """
        Retry immediately instead of waiting out the fallback poll's interval.

        Called from the zeroconf discovery flow (see async_step_zeroconf) when
        this appliance re-announces itself on mDNS - the same discovery that
        drives initial setup already fires on every re-announcement, so this
        rides it rather than running a second, redundant listener. A no-op for
        non-exempt appliance types or while already connected.
        """
        if self._escalate_connectivity_logging or self.connected:
            return
        self.config_entry.async_create_background_task(
            self.hass,
            self._async_poll_reconnect(dt_util.utcnow()),
            "homeconnect_ws nudge reconnect",
        )

    async def async_get_network_info(self) -> list[dict[str, Any]] | None:
        """
        Get the appliance's /ni/info data, shared across the WiFi/ipv4/ipv6 sensors.

        See NETWORK_INFO_COALESCE_WINDOW for why this caches at all rather than
        just forwarding to appliance.get_network_config() every call.
        """
        async with self._network_info_lock:
            now = time.time()
            if (
                self._network_info_fetched_at is not None
                and now - self._network_info_fetched_at
                < NETWORK_INFO_COALESCE_WINDOW.total_seconds()
            ):
                return self._network_info
            if not self.appliance.session.connected:
                # Entities can be added (and their immediate poll-on-add fired)
                # before the appliance's first handshake completes - test-
                # before-setup is exempt for this integration precisely
                # because setup doesn't block on a successful connection.
                # Polling here anyway crashed with a TypeError deep in
                # home_disconnect's message-ID counter, which only gets
                # initialized once the handshake actually finishes. Same
                # guard covers a poll that happens to land during a later
                # disconnect/reconnect window, not just the initial add.
                self.logger.debug("Network info update skipped: not connected")
                return self._network_info
            try:
                self._network_info = await self.appliance.get_network_config()
            except ClientConnectionResetError:
                self.logger.debug("Network info update failed: Connection reset")
            except NotConnectedError:
                self.logger.debug("Network info update failed: Not connected")
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
