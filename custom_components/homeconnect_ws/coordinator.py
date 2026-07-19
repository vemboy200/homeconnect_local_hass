"""Home Connect Coordinator."""

from __future__ import annotations

import asyncio
import logging
import time
from copy import deepcopy
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
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_AES_IV,
    CONF_PSK,
    DOMAIN,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import HCConfigEntry

_LOGGER = logging.getLogger(__name__)

CONNECT_RETRY_INITIAL_DELAY = 5  # seconds
CONNECT_RETRY_MAX_DELAY = 60  # seconds

# Appliance types that routinely cut their own WiFi when powered off between
# cycles. Being unreachable is a normal, expected state for these, not a
# fault, so we don't escalate connect failures past debug-level logging for
# them (see upstream chris-mc1/homeconnect_local_hass issues #274 and #293).
EXPECTED_OFFLINE_APPLIANCE_TYPES = frozenset({"Washer", "Dryer", "WasherDryer"})


class HomeConnectCoordinator(DataUpdateCoordinator):
    """My custom coordinator."""

    config_entry: HCConfigEntry
    appliance: HomeAppliance
    _connecting: bool = True
    connected: bool = False
    _escalate_connectivity_logging: bool

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
        self.appliance = HomeAppliance(
            description=deepcopy(config_entry.data[CONF_DESCRIPTION]),
            host=config_entry.data[CONF_HOST],
            app_name="Homeassistant",
            app_id=config_entry.data[CONF_DEVICE_ID],
            psk64=config_entry.data[CONF_PSK],
            iv64=config_entry.data.get(CONF_AES_IV, None),
            connection_callback=self._connection_state_callback,
        )
        self.disconnect_time = time.time()
        if not self.appliance.info:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="no_device_info",
            )
        self._escalate_connectivity_logging = (
            self.appliance.info.get("type") not in EXPECTED_OFFLINE_APPLIANCE_TYPES
        )

    async def close(self) -> None:
        self._connecting = False
        await self.appliance.close()

    async def _async_setup(self) -> None:
        self.config_entry.async_create_task(self.hass, self._connect())

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
                return
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, CONNECT_RETRY_MAX_DELAY)

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
