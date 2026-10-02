"""Button entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from home_disconnect.entities import Execution
from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .entity import HCEntity
from .helpers import (
    build_full_option_set,
    build_known_option_set,
    create_entities,
    error_decorator,
    needs_full_option_set,
)

if TYPE_CHECKING:
    from home_disconnect.entities import ActiveProgram, Command, Setting
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import HCConfigEntry
    from .entity_descriptions.descriptions_definitions import HCButtonEntityDescription

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    config_entry: HCConfigEntry,
    async_add_entites: AddEntitiesCallback,
) -> None:
    """Set up button platform."""
    entities = create_entities(
        {"button": HCButton, "start_button": HCStartButton}, config_entry.runtime_data
    )
    async_add_entites(entities)


class HCButton(HCEntity, ButtonEntity):
    """Button Entity."""

    _entity: Command | Setting
    entity_description: HCButtonEntityDescription

    @error_decorator
    async def async_press(self) -> None:
        press_value_fn = self.entity_description.press_value_fn
        value = True if press_value_fn is None else press_value_fn()
        await self._entity.set_value(value)


class HCStartButton(HCEntity, ButtonEntity):
    """Start Button Entity."""

    _entity: ActiveProgram
    entity_description: HCButtonEntityDescription

    @property
    def available(self) -> bool:
        # Deliberately skips entity_is_available()'s access check (unlike
        # HCEntity.available): keep this button visible and pressable even
        # when the appliance is currently refusing remote start
        # (BSH.Common.Status.RemoteControlStartAllowed is false) - that's a
        # normal, common appliance state, not an integration bug. async_press
        # below checks access itself and raises a clear, actionable error
        # instead of a silently-greyed-out button, mirroring how the official
        # Home Connect cloud integration keeps its active-program select
        # always available regardless of remote-control state.
        if not self._runtime_data.appliance.session.connected:
            return False
        if not getattr(self._entity, "available", True):
            return False
        selected_program = self._runtime_data.appliance.selected_program
        if selected_program is None:
            return False
        # SELECT_ONLY needs this button too - see generate_start_button.
        return selected_program.execution in (
            Execution.SELECT_AND_START,
            Execution.SELECT_ONLY,
        )

    @error_decorator
    async def async_press(self) -> None:
        selected_program = self._runtime_data.appliance.selected_program
        if selected_program is None:
            return
        # Check BSH.Common.Status.RemoteControlStartAllowed directly rather than
        # ActiveProgram's own access field: ActiveProgram.access is "read" (not
        # writable) whenever the appliance can't currently accept a start for
        # *any* reason - remote start not confirmed, but equally an open door,
        # no program selected on the appliance side, etc. Confusing those would
        # tell a user to go press the physical confirmation button for a
        # problem physically confirming can't fix (e.g. an open door).
        remote_start_allowed = self._runtime_data.appliance.entities.get(
            "BSH.Common.Status.RemoteControlStartAllowed"
        )
        if remote_start_allowed is not None and remote_start_allowed.value is False:
            device_name = self._runtime_data.device_info.get("name") or "your appliance"
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="remote_start_not_allowed",
                translation_placeholders={"device_name": device_name},
            )
        if needs_full_option_set(selected_program):
            # This appliance validates a program write against the program's
            # complete option set and rejects anything less with a 400
            # (confirmed on a Siemens CoffeeMaker and a NEFF oven) - the
            # default merge behaviour below blindly resends every option's
            # raw shadow value, which can still be None for one the
            # appliance hasn't reported yet. Mirrors HCProgram's own
            # _select_with_full_option_set in select.py.
            options = build_full_option_set(self._runtime_data.appliance, selected_program)
            await selected_program.start(options, override_options=True)
        else:
            # The library's default merge resends every READ_WRITE option's
            # raw shadow value, and one the appliance never reported goes out
            # as {"value": null}, which the appliance rejects with 400 for the
            # whole write (seen on a Siemens EQ.9 CoffeeMaker with 1.7.1, where
            # this branch ran). Send the known values only - a hood's Venting
            # program still needs its real level (fork issue #14).
            options = build_known_option_set(self._runtime_data.appliance, selected_program)
            await selected_program.start(options, override_options=True)
