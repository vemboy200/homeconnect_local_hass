"""Fan entities."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any, Final, NamedTuple, override

from home_disconnect.entities import Access
from home_disconnect.message import Action
from home_disconnect.message import Message as HC_Message
from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.event import async_call_later
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
    from datetime import datetime

    from home_disconnect.entities import Entity as HcEntity
    from home_disconnect.entities import Program
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


_POWER_STATE_ENTITY = "BSH.Common.Setting.PowerState"
_OPERATION_STATE_ENTITY = "BSH.Common.Status.OperationState"
_VENTING_PROGRAM_ENTITY = "Cooking.Common.Program.Hood.Venting"  # D80B / 55307
_VENTING_LEVEL_ENTITY = "Cooking.Common.Option.Hood.VentingLevel"  # D80C / 55308
_VENTING_INTENSIVE_LEVEL_ENTITY = "Cooking.Common.Option.Hood.IntensiveLevel"  # D809 / 55305
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
        if self._venting_boost_entity is not None:
            self._set_optimistic_preset(PRESET_NONE)
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

        if self._venting_boost_entity is not None:
            self._set_optimistic_preset(PRESET_NONE)
        await power_state.set_value(off_value)
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
        """Set new preset mode."""
        appliance = self._runtime_data.appliance
        venting_boost = appliance.options[_VENTING_BOOST_ENTITY]
        venting_program = appliance.programs[_VENTING_PROGRAM_ENTITY]
        venting_level = appliance.options[_VENTING_LEVEL_ENTITY]
        venting_intensive_level = appliance.options.get(_VENTING_INTENSIVE_LEVEL_ENTITY)

        options: list[dict[str, Any]] = [
            {"uid": venting_level.uid, "value": 0},
            {"uid": venting_boost.uid, "value": True},
        ]
        # Make intensive level optional (not sure if such a case can happen)
        if venting_intensive_level is not None:
            options.append({"uid": venting_intensive_level.uid, "value": 0})

        message_data: list[dict[str, Any]] = []
        message_data.append({"program": venting_program.uid, "options": options})
        message = HC_Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data=message_data,
        )
        await self._runtime_data.appliance.session.send_sync(message)

    async def stop_boost(self) -> None:
        """Set new preset mode."""
        appliance = self._runtime_data.appliance
        venting_program = appliance.programs[_VENTING_PROGRAM_ENTITY]

        message_data: list[dict[str, Any]] = []
        message_data.append({"program": venting_program.uid, "options": []})
        message = HC_Message(
            resource="/ro/activeProgram",
            action=Action.POST,
            data=message_data,
        )
        await self._runtime_data.appliance.session.send_sync(message)
