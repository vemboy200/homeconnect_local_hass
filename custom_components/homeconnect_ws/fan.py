"""Fan entities."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any, Final, NamedTuple, override

from home_disconnect.entities import Access
from home_disconnect.message import Action
from home_disconnect.message import Message as HC_Message
from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util.percentage import percentage_to_ranged_value, ranged_value_to_percentage

from .const import DOMAIN
from .entity import HCEntity
from .entity_descriptions.common import POWER_OFF_STATE_NAMES
from .helpers import (
    build_full_option_set,
    create_entities,
    entity_is_available,
    error_decorator,
    needs_full_option_set,
)

if TYPE_CHECKING:
    from home_disconnect.entities import Entity as HcEntity
    from home_disconnect.entities import Program
    from homeassistant.core import HomeAssistant
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


_POWER_STATE_ENTITY = "BSH.Common.Setting.PowerState"
_OPERATION_STATE_ENTITY = "BSH.Common.Status.OperationState"
_VENTING_PROGRAM_ENTITY = "Cooking.Common.Program.Hood.Venting" # D80B / 55307
_VENTING_LEVEL_ENTITY = "Cooking.Common.Option.Hood.VentingLevel" # D80C / 55308
_VENTING_INTENSIVE_LEVEL_ENTITY = "Cooking.Common.Option.Hood.IntensiveLevel" # D809 / 55305
_VENTING_BOOST_ENTITY = "Cooking.Common.Option.Hood.Boost" # D801 / 55297
_INACTIVE_OPERATION_STATES = frozenset({"inactive", "ready"})

_HOOD_FAN_STATE_ENTITIES = (
    "BSH.Common.Root.ActiveProgram",
    _OPERATION_STATE_ENTITY,
)


class HCFan(HCEntity, FanEntity):
    """Fan Entity."""

    entity_description: HCFanEntityDescription
    _speed_entities: dict[str, HcEntity]
    _speed_range: tuple[float, float]
    _speed_mapping: list[SpeedMapping]

    def __init__(
        self,
        entity_description: HCFanEntityDescription,
        runtime_data: HCData,
    ) -> None:
        super().__init__(entity_description, runtime_data)

        ventingBoost = self._runtime_data.appliance.options.get(_VENTING_BOOST_ENTITY)

        self._attr_supported_features = (
            FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_OFF | FanEntityFeature.TURN_ON | FanEntityFeature.PRESET_MODE
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

            if ventingBoost is not None:
                self._attr_preset_modes = PRESET_MODES
                self._attr_preset_mode = PRESET_NONE

        self._speed_range = (1, self._attr_speed_count)

    async def async_added_to_hass(self) -> None:
        if self.entity_description.key == "fan_hood":
            appliance = self._runtime_data.appliance
            for name in _HOOD_FAN_STATE_ENTITIES:
                entity = appliance.entities.get(name)
                if entity is not None and entity not in self._entities:
                    self._entities.append(entity)
        await super().async_added_to_hass()

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

    def _venting_program(self) -> Program:
        default_program = self.entity_description.default_program
        if default_program is None:
            msg = "Hood fan is missing default_program"
            raise ServiceValidationError(msg)
        if self._runtime_data.appliance.active_program is not None:
            return self._runtime_data.appliance.active_program
        return self._runtime_data.appliance.programs[default_program]

    def _speed_options(
        self,
        program: Program,
        *,
        entity_name: str | None = None,
        value: int = 0,
    ) -> dict[int, str | int | bool]:
        """Build writable fan option uids for the given program."""
        options: dict[int, str | int | bool] = {}
        # Program.options has no public accessor in the library yet.
        for option in program._options:  # noqa: SLF001
            if option.name not in self._speed_entities:
                continue
            if option.access != Access.READ_WRITE:
                continue
            if entity_name is None or option.name == entity_name:
                options[option.uid] = value
            else:
                options[option.uid] = 0
        return options

    @error_decorator
    async def async_set_percentage(self, percentage: int) -> None:
        new_speed = math.ceil(percentage_to_ranged_value(self._speed_range, percentage))
        if new_speed == 0:
            await self.async_turn_off()
            return

        new_speed_entity: str | None = None
        new_speed_value: int | None = None
        for speed in self._speed_mapping:
            if speed.speed == new_speed:
                new_speed_entity = speed.entity_name
                new_speed_value = speed.entity_value

        if new_speed_entity is None or new_speed_value is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="speed_invalid",
                translation_placeholders={"percentage": str(percentage)},
            )

        program = self._venting_program()
        options = self._speed_options(
            program,
            entity_name=new_speed_entity,
            value=new_speed_value,
        )
        if not options:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="speed_invalid",
                translation_placeholders={"percentage": str(percentage)},
            )

        await program.start(options)
        self.async_write_ha_state()

    @error_decorator
    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        if percentage is None:
            program = self._venting_program()
            # Same 400 BadRequest as the start button / program select: an
            # appliance whose ActiveProgram is flagged fullOptionSet validates
            # a program write against the program's complete option set and
            # rejects an empty one. Confirmed live on a Bosch hood.
            options = (
                build_full_option_set(self._runtime_data.appliance, program)
                if needs_full_option_set(program)
                else {}
            )
            await program.start(options, override_options=True)
        else:
            await self.async_set_percentage(int(percentage))
        self.async_write_ha_state()

    @error_decorator
    async def async_turn_off(self, **kwargs: Any) -> None:
        appliance = self._runtime_data.appliance
        if appliance.active_program is None:
            return

        # A hood has no way to abort a running program: it exposes no
        # AbortProgram command and its programs are all START_ONLY. Both
        # other candidates are dead ends, confirmed live on a DWK81AN60 by
        # reading the WebSocket debug log:
        #   - DELETE /ro/activeProgram is never answered at all, so send_sync
        #     waits for a response that cannot come and raises TimeoutError
        #     (upstream issue #386 describes it working on other appliance
        #     classes, so this stays appliance-specific).
        #   - re-POSTing the venting program with VentingLevel=FanOff gets a
        #     bare RESPONSE and is then silently dropped: no value notify
        #     follows and the fan keeps spinning at its previous stage
        #     (fork issue #17).
        # Powering the appliance off is the only stop it honours, and it is
        # the exact counterpart of starting a program, which the hood answers
        # by switching PowerState to On by itself.
        power_state = appliance.entities.get(_POWER_STATE_ENTITY)
        off_value = None
        if power_state is not None:
            entity_min = getattr(power_state, "min", None)
            entity_max = getattr(power_state, "max", None)
            if entity_min is not None and entity_max is not None:
                # Some appliances declare a wider enum than they actually
                # allow writing - matches generate_power_switch's own
                # settable-range check for this same entity.
                settable = {
                    value
                    for key, value in (power_state.enum or {}).items()
                    if entity_min <= int(key) <= entity_max
                }
            else:
                settable = set((power_state.enum or {}).values())
            off_value = next((n for n in POWER_OFF_STATE_NAMES if n in settable), None)
        if power_state is None or off_value is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_power_off",
            )

        await power_state.set_value(off_value)
        self.async_write_ha_state()

    @override
    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if (self._attr_preset_modes is None
            or preset_mode not in self._attr_preset_modes):
            _LOGGER.warning(
                "Preset mode %s is not valid for fan.",
                preset_mode,
            )
            return
        
        self._attr_preset_mode = preset_mode
        if preset_mode == PRESET_NONE:
            await self.stop_boost()
        elif preset_mode == PRESET_BOOST:
            await self.start_boost()

    async def start_boost(self) -> None:
        """Set new preset mode."""
        appliance = self._runtime_data.appliance
        ventingBoost = appliance.options[_VENTING_BOOST_ENTITY]
        ventingProgram = appliance.programs[_VENTING_PROGRAM_ENTITY]
        ventingLevel = appliance.options[_VENTING_LEVEL_ENTITY]
        ventingIntensiveLevel = appliance.options.get(_VENTING_INTENSIVE_LEVEL_ENTITY)

        options: list[dict[str, Any]] = [
            {"uid": ventingLevel.uid, "value": 0},
            {"uid": ventingBoost.uid, "value": True}
            ]
        # Make intensive level optional (not sure if such a case can happen)
        if ventingIntensiveLevel is not None:
            options.append({"uid": ventingIntensiveLevel.uid, "value": 0})

        message_data: list[dict[str, Any]] = []
        message_data.append({
            "program": ventingProgram.uid,
            "options": options
            })
        message = HC_Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data=message_data,
        )
        await self._runtime_data.appliance.session.send_sync(message)

    async def stop_boost(self) -> None:
        """Set new preset mode."""
        appliance = self._runtime_data.appliance
        ventingProgram = appliance.programs[_VENTING_PROGRAM_ENTITY]

        message_data: list[dict[str, Any]] = []
        message_data.append({
            "program": ventingProgram.uid,
            "options": []
            })
        message = HC_Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data=message_data,
        )
        await self._runtime_data.appliance.session.send_sync(message)
