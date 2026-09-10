"""Select entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from home_disconnect.entities import Access, Execution
from homeassistant.components.select import SelectEntity

from .entity import HCEntity
from .helpers import (
    build_full_option_set,
    create_entities,
    ensure_writable,
    entity_is_available,
    error_decorator,
    needs_full_option_set,
)

if TYPE_CHECKING:
    from home_disconnect.entities import Entity as HcEntity
    from home_disconnect.entities import Program, SelectedProgram
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import HCConfigEntry, HCData
    from .entity_descriptions.descriptions_definitions import HCSelectEntityDescription
PARALLEL_UPDATES = 0

# Some hood appliances expose their SelectedProgram as read-only while the
# programs themselves are Execution.START_ONLY - they're started via
# ActiveProgram instead, so SelectedProgram's own access shouldn't gate this
# select's availability. See issue-comparable upstream PR #391.
_ACTIVE_PROGRAM_ACCESS = (Access.READ_WRITE, Access.WRITE_ONLY)
_SELECTED_PROGRAM_SUFFIX = ".SelectedProgram"


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    config_entry: HCConfigEntry,
    async_add_entites: AddEntitiesCallback,
) -> None:
    """Set up select platform."""
    entities = create_entities(
        {"select": HCSelect, "program": HCProgram},
        config_entry.runtime_data,
    )
    async_add_entites(entities)


class HCSelect(HCEntity, SelectEntity):
    """Select Entity."""

    entity_description: HCSelectEntityDescription

    @property
    def _rev_options(self) -> dict[str, str]:
        """Lowercased value -> real enum value, only meaningful with has_state_translation."""
        if not self.entity_description.has_state_translation:
            return {}
        if self._entity is None or not self._entity.enum:
            return {}
        return {str(value).lower(): value for value in self._settable_enum_values()}

    @property
    def options(self) -> list[str]:
        # Computed live rather than cached once at __init__: unlike a
        # Setting, an Option entity's enum isn't guaranteed to be populated
        # yet by the time entities are constructed (confirmed live on fork
        # issue #17 - HA's own SelectEntity.options raises AttributeError,
        # which kills entity registration outright, if neither this nor
        # entity_description.options is ever set). Falling back to an empty
        # list here is safe either way: current_option already treats
        # anything not in this list as unavailable/None.
        if self.entity_description.options:
            return self.entity_description.options
        if self._entity is not None and self._entity.enum:
            enum_values = self._settable_enum_values()
            if self.entity_description.has_state_translation:
                return [str(value).lower() for value in enum_values]
            return [str(value) for value in enum_values]
        return []

    def _settable_enum_values(self) -> list[str]:
        """Return enum values allowed by the appliance min/max range."""
        if self._entity is None or not self._entity.enum:
            return []
        values: list[str] = []
        entity_min = getattr(self._entity, "min", None)
        entity_max = getattr(self._entity, "max", None)
        for key, enum_value in self._entity.enum.items():
            if entity_min is not None and int(key) < entity_min:
                continue
            if entity_max is not None and int(key) > entity_max:
                continue
            values.append(enum_value)
        return values

    @property
    def current_option(self) -> str | None:
        if (
            self.entity_description.force_option_when_expected_offline is not None
            and self._runtime_data.coordinator.expected_offline
            # A static entity description can't know every appliance model's
            # actual enum in advance - only force to a value this appliance
            # genuinely has, or SelectEntity.state silently degrades to
            # "Unknown" for models missing it (confirmed live on fork issue
            # #7 for the dynamically-generated PowerState case; this guards
            # the same failure mode for statically-declared descriptions).
            and self.entity_description.force_option_when_expected_offline in self.options
        ):
            return self.entity_description.force_option_when_expected_offline
        if self._entity is None:
            return None
        if self.entity_description.has_state_translation:
            value = str(self._entity.value).lower()
            if value in self.options:
                return value
        value = str(self._entity.value)
        if value in self.options:
            return value
        return None

    @error_decorator
    async def async_select_option(self, option: str) -> None:
        if self._entity is None:
            return
        ensure_writable(self._entity)
        if self._rev_options:
            option = self._rev_options[option]
        await self._entity.set_value(option)


class HCProgram(HCSelect):
    """Program select Entity."""

    _entity: SelectedProgram
    _active_program_entity: HcEntity | None = None

    def __init__(
        self,
        entity_description: HCSelectEntityDescription,
        runtime_data: HCData,
    ) -> None:
        super().__init__(entity_description, runtime_data)
        self._programs = entity_description.mapping or {}
        self._rev_programs = {value: key for key, value in self._programs.items()}
        if entity_description.entity and entity_description.entity.endswith(
            _SELECTED_PROGRAM_SUFFIX
        ):
            active_program_entity_name = (
                entity_description.entity.removesuffix(_SELECTED_PROGRAM_SUFFIX) + ".ActiveProgram"
            )
            self._active_program_entity = self._runtime_data.appliance.entities.get(
                active_program_entity_name
            )
            if self._active_program_entity is not None:
                self._entities.append(self._active_program_entity)

    @property
    def options(self) -> list[str]:
        return list(self._programs.values())

    @property
    def available(self) -> bool:
        if super().available:
            return True
        # SelectedProgram itself may be read-only on appliances (e.g. some
        # hoods) whose programs are only startable via ActiveProgram - don't
        # let that gate availability when every mapped program is
        # start-only and ActiveProgram is actually writable.
        if self._active_program_entity is None:
            return False
        return (
            entity_is_available(self._active_program_entity, _ACTIVE_PROGRAM_ACCESS)
            and self._programs_are_start_only()
        )

    def _programs_are_start_only(self) -> bool:
        programs = [self._runtime_data.appliance.programs.get(name) for name in self._programs]
        return bool(programs) and all(
            program is not None and program.execution == Execution.START_ONLY
            for program in programs
        )

    @property
    def current_option(self) -> str | None:
        current_program = self._runtime_data.appliance.selected_program
        if current_program is None:
            current_program = self._runtime_data.appliance.active_program
        if current_program:
            if current_program.name in self._programs:
                return self._programs[current_program.name]
            return current_program.name
        return None

    @error_decorator
    async def async_select_option(self, option: str) -> None:
        selected_program = self._runtime_data.appliance.programs[self._rev_programs[option]]
        if needs_full_option_set(selected_program):
            # This appliance validates a program write against the program's
            # complete option set and rejects anything less with a 400, so
            # neither of the branches below can apply to it (confirmed live on
            # a Bosch HNG6764B6 oven, where every single one of its programs
            # failed to select). Scoped to appliances that actually say so in
            # their device description - see _needs_full_option_set.
            await self._select_with_full_option_set(selected_program)
        elif selected_program.execution in (Execution.SELECT_ONLY, Execution.SELECT_AND_START):
            # override_options=True (send no options) rather than merging in
            # each option's current shared value: a single option UID can have
            # a different valid range depending on which program last set it
            # (confirmed live on fork issues #9/#21 - the same UID sent 160 in
            # a stale, out-of-range value from a previous program and got a
            # 400, but 80 - a value actually valid for the new program -
            # succeeded). The official cloud API selects programs with an
            # empty options list for exactly this reason, letting the
            # appliance apply its own per-program defaults instead. Only
            # start()'s START_ONLY path (see issue #14) actually needs the
            # opposite - some options there have no safe appliance-side
            # default at all - so this doesn't touch that branch.
            #
            # Only this branch and _select_with_full_option_set's SELECT_ONLY
            # branch actually write to SelectedProgram itself - the START_ONLY
            # branch below writes ActiveProgram instead, so SelectedProgram
            # being permanently read-only-by-design on those appliances (see
            # generate_start_button) must not block it.
            ensure_writable(self._entity)
            await selected_program.select(override_options=True)
        elif selected_program.execution == Execution.START_ONLY:
            await selected_program.start()

    async def _select_with_full_option_set(self, program: Program) -> None:
        """Write program and options together, for appliances that demand both."""
        options = build_full_option_set(self._runtime_data.appliance, program)
        if program.execution == Execution.SELECT_ONLY:
            ensure_writable(self._entity)
            await program.select(options, override_options=True)
        else:
            # SELECT_AND_START and START_ONLY both go to /ro/activeProgram: an
            # appliance that combines selecting and starting into a single
            # operation rejects a bare POST to /ro/selectedProgram with a 400.
            await program.start(options, override_options=True)
