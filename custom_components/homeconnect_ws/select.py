"""Select entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from home_disconnect.entities import Execution
from homeassistant.components.select import SelectEntity

from .entity import HCEntity
from .helpers import create_entities, error_decorator

if TYPE_CHECKING:
    from home_disconnect.entities import SelectedProgram
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import HCConfigEntry, HCData
    from .entity_descriptions.descriptions_definitions import HCSelectEntityDescription
PARALLEL_UPDATES = 0


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

    def __init__(
        self,
        entity_description: HCSelectEntityDescription,
        runtime_data: HCData,
    ) -> None:
        super().__init__(entity_description, runtime_data)
        self._programs = entity_description.mapping or {}
        self._rev_programs = {value: key for key, value in self._programs.items()}

    @property
    def options(self) -> list[str]:
        return list(self._programs.values())

    @property
    def current_option(self) -> str | None:
        if self._runtime_data.appliance.selected_program:
            if self._runtime_data.appliance.selected_program.name in self._programs:
                return self._programs[self._runtime_data.appliance.selected_program.name]
            return self._runtime_data.appliance.selected_program.name
        return None

    @error_decorator
    async def async_select_option(self, option: str) -> None:
        selected_program = self._runtime_data.appliance.programs[self._rev_programs[option]]
        if selected_program.execution in (Execution.SELECT_ONLY, Execution.SELECT_AND_START):
            await selected_program.select()
        elif selected_program.execution == Execution.START_ONLY:
            await selected_program.start()
