"""Button entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from home_disconnect import (
    DelayTooLongError,
    ProgramDurationUnknownError,
    RemoteStartNotAllowedError,
)
from home_disconnect.entities import Execution
from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .entity import HCEntity
from .helpers import (
    create_entities,
    error_decorator,
    remote_start_error,
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
    # A button has no value to keep showing, so a read-only one (e.g. the
    # clock button while "Synchronize time with server" is on) goes
    # unavailable instead of staying pressable only to raise an error.
    # HCStartButton is deliberately different - see its available.
    _show_when_locked = False

    @error_decorator
    async def async_press(self) -> None:
        press_fn = self.entity_description.press_fn
        if press_fn is None:
            await self._entity.set_value(True)
        else:
            await press_fn(self._runtime_data.appliance)


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
        if not self._runtime_data.appliance.connected:
            return False
        # None means the appliance hasn't said; only an explicit False hides it.
        if self._entity.available is False:
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
        # The library picks the options: a full set on appliances that want
        # one (a Siemens CoffeeMaker, a NEFF oven), otherwise only the values
        # the appliance has reported - an option sent as null makes it reject
        # the whole start with 400 (a hood still needs its real venting level,
        # fork issue #14).
        # The library also turns the "Delay start" select's choice into StartInRelative or
        # FinishInRelative, the only form some appliances accept it in (#146).
        try:
            await self._runtime_data.appliance.start_program(
                selected_program, delay=self._runtime_data.delay_start.seconds
            )
        except DelayTooLongError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="delay_start_too_long",
                translation_placeholders={"max_hours": str(err.maximum // 3600)},
            ) from None
        except ProgramDurationUnknownError:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="delay_start_duration_unknown",
            ) from None
        except RemoteStartNotAllowedError:
            # Only for BSH.Common.Status.RemoteControlStartAllowed, not ActiveProgram being
            # read-only: that also happens for other reasons (an open door), which going to the
            # appliance to allow remote start wouldn't fix.
            raise remote_start_error(self._runtime_data) from None
        self._runtime_data.delay_start.reset()
