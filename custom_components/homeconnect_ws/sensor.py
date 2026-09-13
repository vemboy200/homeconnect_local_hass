"""Sensor entities."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any, ClassVar, cast

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


# HCWiFI and the ipv4/ipv6 address sensors are the only should_poll entities in
# this platform, so this interval only affects them. Their /ni/info data is only
# available via an active request (there's no push notification for any of it),
# and the appliance is stationary, so none of it has reason to change minute-to-
# minute. Poll infrequently: enough to catch a real change/degradation trend,
# without adding needless traffic to the appliance's connection. All three share
# one fetch per interval rather than issuing three - see
# coordinator.async_get_network_info.
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
            "ipv4": HCIPv4Address,
            "ipv6": HCIPv6Address,
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
        network_info = await self._runtime_data.coordinator.async_get_network_info()
        if network_info and isinstance(network_info, list) and "rssi" in network_info[0]:
            self._attr_native_value = network_info[0]["rssi"]
        else:
            _LOGGER.debug("WiFi update failed: unexpected response format: %s", network_info)


class HCIPAddress(HCEntity, SensorEntity):
    """
    Base for the IPv4/IPv6 address sensors.

    Polled the same way as HCWiFI (see its docstring/should_poll override),
    sharing the same /ni/info data through the coordinator's cache rather than
    each issuing its own request - see NETWORK_INFO_COALESCE_WINDOW in
    coordinator.py.
    """

    entity_description: HCSensorEntityDescription
    # Set by the two concrete subclasses below - "ipV4" or "ipV6", matching
    # the key /ni/info nests each interface's address block under.
    _interface_key: ClassVar[str]

    @property
    def should_poll(self) -> bool:
        # See HCWiFI.should_poll for why this override is required.
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Without this, the platform's SCAN_INTERVAL timer wouldn't fire the
        # first poll until a full interval after setup/reload - get a value
        # immediately instead of sitting at unknown for up to an hour.
        await self.async_update()
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # HCEntity's own extra_state_attributes builds off entity_description.
        # extra_attributes (a real BSH entity's value) - these sensors have no
        # backing BSH entity at all, so that machinery doesn't apply here.
        return self._address_attributes

    def __init__(
        self,
        entity_description: HCSensorEntityDescription,
        runtime_data: HCData,
    ) -> None:
        super().__init__(entity_description, runtime_data)
        self._address_attributes: dict[str, Any] = {}

    async def async_update(self) -> None:
        network_info = await self._runtime_data.coordinator.async_get_network_info()
        if not network_info or not isinstance(network_info, list):
            _LOGGER.debug(
                "%s update failed: unexpected response format: %s",
                self.entity_description.key,
                network_info,
            )
            return
        address_info = network_info[0].get(self._interface_key)
        if not isinstance(address_info, dict):
            # Normal, not an error: an appliance with only an IPv4 or only an
            # IPv6 address simply won't have the other key in its /ni/info
            # response at all.
            self._attr_native_value = None
            self._address_attributes = {}
            return
        self._attr_native_value = address_info.get("ipAddress")
        self._address_attributes = {
            "prefix_size": address_info.get("prefixSize"),
            "gateway": address_info.get("gateway"),
            "dns_server": address_info.get("dnsServer"),
        }


class HCIPv4Address(HCIPAddress):
    """IPv4 address Sensor Entity."""

    _interface_key = "ipV4"


class HCIPv6Address(HCIPAddress):
    """IPv6 address Sensor Entity."""

    _interface_key = "ipV6"
