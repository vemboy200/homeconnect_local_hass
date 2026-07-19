"""Sensor entities."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from aiohttp.client_exceptions import ClientConnectionResetError
from home_disconnect import NotConnectedError
from homeassistant.components.sensor import SensorEntity

from .entity import HCEntity
from .helpers import create_entities

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import HCConfigEntry, HCData
    from .entity_descriptions.descriptions_definitions import HCSensorEntityDescription

PARALLEL_UPDATES = 0

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

        if self._entity.enum:
            if self.entity_description.has_state_translation:
                self._attr_options = [str(value).lower() for value in self._entity.enum.values()]
            else:
                self._attr_options = [str(value) for value in self._entity.enum.values()]

    @property
    def native_value(self) -> int | float | str:
        if self._entity.value is None:
            return None
        if self._entity.enum and self.entity_description.has_state_translation:
            return str(self._entity.value).lower()
        return self._entity.value


class HCEventSensor(HCEntity, SensorEntity):
    """Event Sensor Entity."""

    entity_description: HCSensorEntityDescription

    @property
    def native_value(self) -> str:
        if self.entity_description.options:
            for entity, value in zip(self._entities, self.entity_description.options, strict=False):
                if (entity.enum is not None and entity.value in {"Present", "Confirmed"}) or (
                    entity.enum is None and bool(entity.value)
                ):
                    return value
        return self.entity_description.options[-1]

    @property
    def available(self) -> bool:
        return self._runtime_data.appliance.session.connected


class HCActiveProgram(HCSensor):
    """Active Program Sensor Entity."""

    entity_description: HCSensorEntityDescription

    def __init__(
        self,
        entity_description: HCSensorEntityDescription,
        runtime_data: HCData,
    ) -> None:
        super().__init__(entity_description, runtime_data)
        self._attr_options = list(entity_description.mapping.values())

    @property
    def native_value(self) -> str | None:
        if self._runtime_data.appliance.active_program:
            if self._runtime_data.appliance.active_program.name in self.entity_description.mapping:
                return self.entity_description.mapping[
                    self._runtime_data.appliance.active_program.name
                ]
            return self._runtime_data.appliance.active_program.name
        return None


class HCWiFI(HCEntity, SensorEntity):
    """WiFi signal Sensor Entity, polled since the appliance never pushes it."""

    _attr_should_poll = True

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
        if value is None:
            return "mdi:wifi-strength-outline"
        magnitude = abs(value)
        for threshold, icon in _WIFI_STRENGTH_ICONS:
            if magnitude < threshold:
                return icon
        return "mdi:wifi-strength-1-alert"

    async def async_update(self) -> None:
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
