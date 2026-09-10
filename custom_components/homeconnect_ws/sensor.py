"""Sensor entities."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, cast

from aiohttp.client_exceptions import ClientConnectionResetError
from home_disconnect import NotConnectedError
from homeassistant.components.sensor import SensorEntity

from .entity import HCEntity
from .helpers import create_entities

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from home_disconnect import HomeAppliance
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import HCConfigEntry, HCData
    from .entity_descriptions.descriptions_definitions import HCSensorEntityDescription

PARALLEL_UPDATES = 0

# Mirrors entity_descriptions.common.POWER_OFF_STATE_NAMES - kept local rather
# than shared since this is the only place outside fan.py that needs it, and
# importing across the entity_descriptions/helpers boundary here risks a
# circular import (entity_descriptions already imports from helpers).
_POWER_OFF_STATE_NAMES = ("Off", "MainsOff")
_POWER_STATE_ENTITY = "BSH.Common.Setting.PowerState"
_ACTIVE_PROGRAM_ENTITY = "BSH.Common.Root.ActiveProgram"
_NO_ACTIVE_PROGRAM_TRIGGER_ENTITIES = (_ACTIVE_PROGRAM_ENTITY, _POWER_STATE_ENTITY)


def _no_active_program_and_off(appliance: HomeAppliance) -> bool:
    """
    Whether nothing is running and the appliance has powered itself off.

    Distinct from clear_on_expected_offline/coordinator.expected_offline,
    which only covers laundry appliances that cut their own WiFi on power-off
    (see EXPECTED_OFFLINE_APPLIANCE_TYPES) - this instead covers appliances
    that stay connected and reachable but stop pushing updates for
    Option-based status (phase, progress) once idle, so those values freeze
    at whatever they last showed while a program was still running.
    """
    if appliance.active_program is not None:
        return False
    power_state = appliance.entities.get(_POWER_STATE_ENTITY)
    return power_state is not None and power_state.value in _POWER_OFF_STATE_NAMES


# HCWiFI is the only should_poll entity in this platform, so this interval only
# affects it. WiFi signal strength is only available via an active /ni/info request
# (there's no push notification for it), and the appliance is stationary, so its
# signal has no reason to change minute-to-minute. Poll infrequently: enough to catch
# a real degradation trend, without adding needless traffic to the appliance's
# connection.
SCAN_INTERVAL = timedelta(hours=1)

# (exclusive upper bound on |RSSI| in dBm, icon) - checked in order, first match wins.
# WiFi typically drops the connection entirely around -90 dBm, so a reading that
# weak while still connected is either about to drop or already unreliable.
_WIFI_STRENGTH_ICONS = (
    (60, "mdi:wifi-strength-4"),
    (70, "mdi:wifi-strength-3"),
    (80, "mdi:wifi-strength-2"),
    (90, "mdi:wifi-strength-1"),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    config_entry: HCConfigEntry,
    async_add_entites: AddEntitiesCallback,
) -> None:
    """Set up sensor platform."""
    entities = create_entities(
        {
            "sensor": HCSensor,
            "event_sensor": HCEventSensor,
            "active_program": HCActiveProgram,
            "wifi": HCWiFI,
        },
        config_entry.runtime_data,
    )
    async_add_entites(entities)


class HCSensor(HCEntity, SensorEntity):
    """Sensor Entity."""

    entity_description: HCSensorEntityDescription

    def __init__(
        self,
        entity_description: HCSensorEntityDescription,
        runtime_data: HCData,
    ) -> None:
        super().__init__(entity_description, runtime_data)

        if self._entity is not None and self._entity.enum:
            if self.entity_description.has_state_translation:
                self._attr_options = [str(value).lower() for value in self._entity.enum.values()]
            else:
                self._attr_options = [str(value) for value in self._entity.enum.values()]

        if (
            entity_description.force_value_when_no_active_program is not None
            or entity_description.unavailable_when_no_active_program
        ):
            # This sensor's own backing entity (e.g. program_phase) is
            # exactly the one that stops getting fresh NOTIFYs once idle -
            # that's the bug being worked around. Without also listening to
            # ActiveProgram/PowerState, nothing would ever call
            # async_write_ha_state() again to make HA re-evaluate
            # native_value/available against the new idle state. Same
            # pattern as fan.py's _HOOD_FAN_STATE_ENTITIES.
            for name in _NO_ACTIVE_PROGRAM_TRIGGER_ENTITIES:
                trigger_entity = runtime_data.appliance.entities.get(name)
                if trigger_entity is not None and trigger_entity not in self._entities:
                    self._entities.append(trigger_entity)

    @property
    def native_value(self) -> int | float | str | None:
        if self.entity_description.clear_on_expected_offline and (
            self._runtime_data.coordinator.expected_offline
        ):
            return None
        if (
            self.entity_description.force_option_when_expected_offline is not None
            and self._runtime_data.coordinator.expected_offline
            # See HCSelect.current_option - only force to a value this
            # appliance's own enum actually has.
            and (
                self._attr_options is None
                or self.entity_description.force_option_when_expected_offline in self._attr_options
            )
        ):
            return self.entity_description.force_option_when_expected_offline
        if (
            self.entity_description.force_value_when_no_active_program is not None
            and _no_active_program_and_off(self._runtime_data.appliance)
            and (
                self._attr_options is None
                or self.entity_description.force_value_when_no_active_program in self._attr_options
            )
        ):
            return self.entity_description.force_value_when_no_active_program
        if self._entity is None or self._entity.value is None:
            return None
        if self._entity.enum and self.entity_description.has_state_translation:
            return str(self._entity.value).lower()
        return cast("int | float | str", self._entity.value)

    @property
    def available(self) -> bool:
        if self.entity_description.unavailable_when_no_active_program and (
            _no_active_program_and_off(self._runtime_data.appliance)
        ):
            return False
        return super().available


class HCEventSensor(HCEntity, SensorEntity):
    """Event Sensor Entity."""

    entity_description: HCSensorEntityDescription

    @property
    def native_value(self) -> str:
        options = self.entity_description.options or []
        for entity, value in zip(self._entities, options, strict=False):
            if (entity.enum is not None and entity.value in {"Present", "Confirmed"}) or (
                entity.enum is None and bool(entity.value)
            ):
                return value
        return options[-1]

    @property
    def available(self) -> bool:
        return (
            self._runtime_data.appliance.session.connected
            or self._runtime_data.coordinator.expected_offline
        )


class HCActiveProgram(HCSensor):
    """Active Program Sensor Entity."""

    def __init__(
        self,
        entity_description: HCSensorEntityDescription,
        runtime_data: HCData,
    ) -> None:
        super().__init__(entity_description, runtime_data)
        self._attr_options = list((entity_description.mapping or {}).values())

    @property
    def native_value(self) -> str | None:
        if self.entity_description.clear_on_expected_offline and (
            self._runtime_data.coordinator.expected_offline
        ):
            return None
        if self._runtime_data.appliance.active_program:
            mapping = self.entity_description.mapping or {}
            if self._runtime_data.appliance.active_program.name in mapping:
                return mapping[self._runtime_data.appliance.active_program.name]
            return self._runtime_data.appliance.active_program.name
        return None


class HCWiFI(HCEntity, SensorEntity):
    """WiFi signal Sensor Entity, polled since the appliance never pushes it."""

    entity_description: HCSensorEntityDescription

    @property
    def should_poll(self) -> bool:
        # HCEntity inherits from CoordinatorEntity, whose should_poll is a hardcoded
        # False and takes priority over Entity's (which reads _attr_should_poll) in
        # the MRO - setting _attr_should_poll here alone is silently ignored. This
        # explicit override is required for the SCAN_INTERVAL polling below to
        # actually run at all.
        return True

    def __init__(
        self,
        entity_description: HCSensorEntityDescription,
        runtime_data: HCData,
    ) -> None:
        super().__init__(entity_description, runtime_data)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Without this, the platform's SCAN_INTERVAL timer wouldn't fire the
        # first poll until a full interval after setup/reload - get a value
        # immediately instead of sitting at unknown for up to an hour.
        await self.async_update()
        self.async_write_ha_state()

    @property
    def icon(self) -> str:
        value = self.native_value
        if not isinstance(value, int | float):
            return "mdi:wifi-strength-outline"
        magnitude = abs(value)
        for threshold, icon in _WIFI_STRENGTH_ICONS:
            if magnitude < threshold:
                return icon
        return "mdi:wifi-strength-1-alert"

    async def async_update(self) -> None:
        if not self._runtime_data.appliance.session.connected:
            # Entities can be added (and the immediate poll below fired) before
            # the appliance's first handshake completes - test-before-setup is
            # exempt for this integration precisely because setup doesn't block
            # on a successful connection. Polling here anyway crashed with a
            # TypeError deep in home_disconnect's message-ID counter, which
            # only gets initialized once the handshake actually finishes. Same
            # guard covers a poll that happens to land during a later
            # disconnect/reconnect window, not just the initial add.
            _LOGGER.debug("WiFi update skipped: not connected")
            return
        try:
            network_info = await self._runtime_data.appliance.get_network_config()
            if network_info and isinstance(network_info, list) and "rssi" in network_info[0]:
                self._attr_native_value = network_info[0]["rssi"]
            else:
                _LOGGER.debug("WiFi update failed: unexpected response format: %s", network_info)
        except ClientConnectionResetError:
            _LOGGER.debug("WiFi update failed: Connection reset")
        except NotConnectedError:
            _LOGGER.debug("WiFi update failed: Not connected")
