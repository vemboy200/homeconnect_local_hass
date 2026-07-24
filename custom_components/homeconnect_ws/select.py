"""Select entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from home_disconnect.entities import Access, Execution
from homeassistant.components.select import SelectEntity

from .entity import HCEntity
from .helpers import create_entities, entity_is_available, error_decorator

if TYPE_CHECKING:
    from home_disconnect.entities import Entity as HcEntity
    from home_disconnect.entities import SelectedProgram
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
    _rev_options: dict[str, str]

    def __init__(
        self,
        entity_description: HCSelectEntityDescription,
        runtime_data: HCData,
    ) -> None:
        super().__init__(entity_description, runtime_data)

        self._rev_options = {}
        if entity_description.options:
            self._attr_options = entity_description.options
        elif self._entity is not None and self._entity.enum:
            enum_values = self._settable_enum_values()
            self._attr_options = []
            if self.entity_description.has_state_translation:
                for value in enum_values:
                    self._attr_options.append(str(value).lower())
            else:
                for value in enum_values:
                    self._attr_options.append(str(value))

        if self.entity_description.has_state_translation and (
            self._entity is not None and self._entity.enum
        ):
            for value in self._settable_enum_values():
                self._rev_options[str(value).lower()] = value

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
        ):
            return self.entity_description.force_option_when_expected_offline
        if self._entity is None:
            return None
        if self.entity_description.has_state_translation:
            value = str(self._entity.value).lower()
            if value in self._attr_options:
                return value
        value = str(self._entity.value)
        if value in self._attr_options:
            return value
        return None

    @error_decorator
    async def async_select_option(self, option: str) -> None:
        if self._entity is None:
            return
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
        if selected_program.execution in (Execution.SELECT_ONLY, Execution.SELECT_AND_START):
            await selected_program.select()
        elif selected_program.execution == Execution.START_ONLY:
            # Avoid sending uninitialized option shadow values for start-only
            # programs that were never selected first - let the appliance
            # use its own defaults instead.
            await selected_program.start(override_options=True)
