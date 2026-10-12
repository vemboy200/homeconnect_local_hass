"""Fan entities."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any, Final, NamedTuple, override

from home_disconnect import AccessError
from homeassistant.components.fan import FanEntity
from homeassistant.components.fan.const import FanEntityFeature
from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.event import async_call_later
from homeassistant.util.percentage import percentage_to_ranged_value, ranged_value_to_percentage

from .const import DOMAIN
from .entity import HCEntity
from .helpers import (
    create_entities,
    entity_is_available,
    error_decorator,
)

if TYPE_CHECKING:
    from datetime import datetime

    from home_disconnect.entities import Entity as HcEntity
    from homeassistant.core import CALLBACK_TYPE, HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import HCConfigEntry, HCData
    from .entity_descriptions.descriptions_definitions import HCFanEntityDescription

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

PRESET_NONE = "None"
PRESET_BOOST = "Boost"

PRESET_MODES: Final = [
    PRESET_NONE,
    PRESET_BOOST,
]

# The appliance doesn't confirm a boost start/stop right away, and reverts
# boost on its own once its own timer elapses with no "still pending" signal
# in between (see PR #55's discussion) - so preset_mode below always reads
# the appliance's own live Boost value, and this is just how long a
# just-requested change is shown immediately rather than waiting on that.
_OPTIMISTIC_PRESET_DURATION = 8


class SpeedMapping(NamedTuple):
    """Mapping of entity name / value and speed."""

    entity_name: str
    entity_value: int
    speed: int


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    config_entry: HCConfigEntry,
    async_add_entites: AddEntitiesCallback,
) -> None:
    """Set up fan platform."""
    entities = create_entities({"fan": HCFan}, config_entry.runtime_data)
    async_add_entites(entities)


_OPERATION_STATE_ENTITY = "BSH.Common.Status.OperationState"
_VENTING_BOOST_ENTITY = "Cooking.Common.Option.Hood.Boost"  # D801 / 55297
_INACTIVE_OPERATION_STATES = frozenset({"inactive", "ready"})

_HOOD_FAN_STATE_ENTITIES = (
    "BSH.Common.Root.ActiveProgram",
    _OPERATION_STATE_ENTITY,
    _VENTING_BOOST_ENTITY,
)


class HCFan(HCEntity, FanEntity):
    """Fan Entity."""

    entity_description: HCFanEntityDescription
    _speed_entities: dict[str, HcEntity]
    _speed_range: tuple[float, float]
    _speed_mapping: list[SpeedMapping]
    _venting_boost_entity: HcEntity | None
    _optimistic_preset_mode: str | None
    _optimistic_preset_clear: CALLBACK_TYPE | None

    def __init__(
        self,
        entity_description: HCFanEntityDescription,
        runtime_data: HCData,
    ) -> None:
        super().__init__(entity_description, runtime_data)

        self._attr_supported_features = (
            FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_OFF | FanEntityFeature.TURN_ON
        )
        self._speed_mapping = []
        self._speed_entities = {}
        self._attr_speed_count = 0
        for entity_name in entity_description.entities or []:
            entity = self._runtime_data.appliance.entities[entity_name]
            self._speed_entities[entity_name] = entity
            for option in entity.enum or {}:
                if option != 0:
                    self._attr_speed_count += 1
                    self._speed_mapping.append(
                        SpeedMapping(
                            entity_name=entity_name,
                            entity_value=option,
                            speed=self._attr_speed_count,
                        )
                    )

        self._optimistic_preset_mode = None
        self._optimistic_preset_clear = None
        self._venting_boost_entity = self._runtime_data.appliance.options.get(_VENTING_BOOST_ENTITY)
        if self._venting_boost_entity is not None:
            self._attr_supported_features |= FanEntityFeature.PRESET_MODE
            self._attr_preset_modes = PRESET_MODES

        self._speed_range = (1, self._attr_speed_count)

    async def async_added_to_hass(self) -> None:
        if self.entity_description.key == "fan_hood":
            appliance = self._runtime_data.appliance
            for name in _HOOD_FAN_STATE_ENTITIES:
                entity = appliance.entities.get(name)
                if entity is not None and entity not in self._entities:
                    self._entities.append(entity)
        await super().async_added_to_hass()

    async def async_will_remove_from_hass(self) -> None:
        if self._optimistic_preset_clear is not None:
            self._optimistic_preset_clear()
        await super().async_will_remove_from_hass()

    @property
    def preset_mode(self) -> str | None:
        # Optimistic first: bridges the gap until the appliance confirms a
        # just-requested boost start/stop, or until it reverts boost on its
        # own - see _OPTIMISTIC_PRESET_DURATION above.
        if self._optimistic_preset_mode is not None:
            return self._optimistic_preset_mode
        if self._venting_boost_entity is None:
            return None
        return PRESET_BOOST if self._venting_boost_entity.value_raw else PRESET_NONE

    @callback
    def _set_optimistic_preset(self, preset_mode: str) -> None:
        """Show `preset_mode` immediately, then defer back to the live value above."""
        if self._optimistic_preset_clear is not None:
            self._optimistic_preset_clear()
        self._optimistic_preset_mode = preset_mode
        self._optimistic_preset_clear = async_call_later(
            self.hass, _OPTIMISTIC_PRESET_DURATION, self._clear_optimistic_preset
        )
        self.async_write_ha_state()

    @callback
    def _clear_optimistic_preset(self, _now: datetime) -> None:
        self._optimistic_preset_mode = None
        self._optimistic_preset_clear = None
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        available = super().available
        for entity in self._speed_entities.values():
            available &= entity_is_available(entity, self.entity_description.available_access)
        return available

    @property
    def is_on(self) -> bool:
        appliance = self._runtime_data.appliance
        # Some hoods keep reporting an active Venting program with a non-zero
        # venting level after being switched off. OperationState is the
        # authoritative signal in that case.
        operation_state = appliance.entities.get(_OPERATION_STATE_ENTITY)
        if (
            operation_state is not None
            and str(operation_state.value or "").lower() in _INACTIVE_OPERATION_STATES
        ):
            return False
        if appliance.active_program is None:
            return False
        return any(entity.value_raw not in (None, 0) for entity in self._speed_entities.values())

    @property
    def percentage(self) -> int | None:
        if not self.is_on:
            return 0
        for speed in self._speed_mapping:
            if self._speed_entities[speed.entity_name].value_raw == speed.entity_value:
                return ranged_value_to_percentage(self._speed_range, speed.speed)
        return 0

    @error_decorator
    async def async_set_percentage(self, percentage: int) -> None:
        new_speed = math.ceil(percentage_to_ranged_value(self._speed_range, percentage))
        if new_speed == 0:
            await self.async_turn_off()
            return

        speed = next((speed for speed in self._speed_mapping if speed.speed == new_speed), None)
        if speed is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="speed_invalid",
                translation_placeholders={"percentage": str(percentage)},
            )

        await self._runtime_data.appliance.set_fan_level(speed.entity_name, speed.entity_value)
        self.async_write_ha_state()

    @error_decorator
    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        if self._venting_boost_entity is not None:
            self._set_optimistic_preset(PRESET_NONE)
        if percentage is None:
            await self._runtime_data.appliance.start_fan()
        else:
            await self.async_set_percentage(int(percentage))
        self.async_write_ha_state()

    @error_decorator
    async def async_turn_off(self, **kwargs: Any) -> None:
        appliance = self._runtime_data.appliance
        if appliance.active_program is None:
            return

        # A hood has no way to abort a running program: it exposes no AbortProgram command, its
        # programs are all START_ONLY, DELETE /ro/activeProgram is never answered and re-starting
        # Venting with the level at FanOff is ignored (DWK81AN60, fork issue #17). Powering the
        # appliance off is the only stop it honours.
        if self._venting_boost_entity is not None:
            self._set_optimistic_preset(PRESET_NONE)
        try:
            await appliance.power_off()
        except AccessError:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_power_off",
            ) from None
        self.async_write_ha_state()

    @override
    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if self._attr_preset_modes is None or preset_mode not in self._attr_preset_modes:
            _LOGGER.warning(
                "Preset mode %s is not valid for fan.",
                preset_mode,
            )
            return

        if preset_mode == PRESET_NONE:
            await self.stop_boost()
        elif preset_mode == PRESET_BOOST:
            await self.start_boost()
        self._set_optimistic_preset(preset_mode)

    async def start_boost(self) -> None:
        """Turn boost on."""
        await self._runtime_data.appliance.set_boost(on=True)

    async def stop_boost(self) -> None:
        """Turn boost off."""
        await self._runtime_data.appliance.set_boost(on=False)
