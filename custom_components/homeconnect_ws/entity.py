"""Base Entity."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from home_disconnect.entities import Access, Option
from home_disconnect.keys import SettingKey
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import HomeConnectCoordinator
from .helpers import entity_is_available, is_lockable, is_locked

if TYPE_CHECKING:
    from home_disconnect.entities import Entity as HcEntity
    from home_disconnect.entities import Program
    from homeassistant.helpers.device_registry import DeviceInfo

    from . import HCData
    from .entity_descriptions.descriptions_definitions import (
        ExtraAttributeDict,
        HCEntityDescription,
    )

_LOGGER = logging.getLogger(__name__)

TEMPERATURE_UNIT_ENTITY = SettingKey.BSH_COMMON_TEMPERATURE_UNIT
# BSH.Common.Setting.TemperatureUnit values
_APPLIANCE_TEMPERATURE_UNITS = {
    "Celsius": UnitOfTemperature.CELSIUS,
    "Fahrenheit": UnitOfTemperature.FAHRENHEIT,
}


class HCEntity(CoordinatorEntity[HomeConnectCoordinator], Entity):
    """Base Entity."""

    entity_description: HCEntityDescription
    _attr_has_entity_name = True
    _entity: HcEntity | None = None
    _entities: list[HcEntity | Program]
    _extra_attributes: list[ExtraAttributeDict]
    _has_callback: bool = False
    # Whether a locked (read-only) Option/Setting/SelectedProgram stays
    # visible with a readonly attribute instead of going unavailable. Off for
    # entities that have no state to show while locked, like buttons.
    _show_when_locked: bool = True
    # For a temperature reported in both units: the backing entity per unit,
    # and the appliance's temperature unit setting that picks between them.
    _unit_entities: dict[str, HcEntity] | None = None
    _temperature_unit_entity: HcEntity | None = None
    # The unit of the backing entity _follow_temperature_unit picked, if any.
    # The number and sensor entities show their value in it.
    _temperature_unit: str | None = None
    # For a feature under several names: the backing entity per name, in order.
    _alternates: list[HcEntity] | None = None

    def __init__(
        self,
        entity_description: HCEntityDescription,
        runtime_data: HCData,
    ) -> None:
        super().__init__(runtime_data.coordinator)
        self._runtime_data = runtime_data
        self.entity_description = entity_description
        self._attr_unique_id = f"{runtime_data.appliance.info['deviceID']}-{entity_description.key}"
        self._attr_device_info: DeviceInfo = runtime_data.device_info
        if entity_description.translation_key is None:
            self._attr_translation_key = entity_description.key

        self._entities = []
        self._extra_attributes = []
        if entity_description.entity:
            self._entity = self._runtime_data.appliance.entities[entity_description.entity]
            self._entities.append(self._runtime_data.appliance.entities[entity_description.entity])
        self._set_up_unit_entities()
        self._set_up_alternate_entities()
        if entity_description.entities:
            for entity_name in entity_description.entities:
                self._entities.append(self._runtime_data.appliance.entities[entity_name])
        if entity_description.extra_attributes:
            for extra_attribute in entity_description.extra_attributes:
                if extra_attribute["entity"] in self._runtime_data.appliance.entities:
                    self._extra_attributes.append(extra_attribute)
        if isinstance(self._entity, Option):
            # Whether an option is available depends on the selected and the active program
            appliance_entities = self._runtime_data.appliance.entities
            for program_root in (
                appliance_entities.selected_program,
                appliance_entities.active_program,
            ):
                if program_root is not None and program_root not in self._entities:
                    self._entities.append(program_root)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        for entity in self._entities:
            entity.register_callback(self.callback)

    async def async_will_remove_from_hass(self) -> None:
        for entity in self._entities:
            entity.unregister_callback(self.callback)

    @property
    def available(self) -> bool:
        connected_or_expected_offline = (
            self._runtime_data.appliance.connected
            or self._runtime_data.coordinator.expected_offline
        )
        available_access = self.entity_description.available_access
        if available_access is not None and self._show_when_locked and is_locked(self._entity):
            # Home Connect itself shows a locked entity (an Option, Setting or
            # SelectedProgram) as visible-but-disabled rather than hiding it
            # (confirmed live on fork issue #59) - Access.READ means "still
            # readable", so widen the check instead of going unavailable and
            # hiding the current value along with the control.
            available_access = (*available_access, Access.READ)
        return (
            connected_or_expected_offline
            and entity_is_available(self._entity, available_access)
            and self._used_by_program()
        )

    def _used_by_program(self) -> bool:
        """
        Return False if the active (or else the selected) program doesn't use this option.

        The profile lists each program's options: an oven's hot air takes a setpoint
        temperature but no grill level, a microwave program neither. Such an option can't be
        set while that program is selected or runs. Without a program, or for a program that
        lists no options, nothing changes.
        """
        if not isinstance(self._entity, Option):
            return True
        appliance = self._runtime_data.appliance
        program = appliance.active_program or appliance.selected_program
        if program is None:
            return True
        options = program.options
        return not options or self._entity in options

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        extra_state_attributes: dict[str, Any] = {}
        if self._show_when_locked and is_lockable(self._entity):
            # Always present (not just when locked) so a template/custom card
            # can rely on it existing rather than treating "missing" as false.
            extra_state_attributes["readonly"] = is_locked(self._entity)
        for description in self._extra_attributes:
            entity = self._runtime_data.appliance.entities[description["entity"]]
            if "value_fn" in description:
                try:
                    extra_state_attributes[description["name"]] = description["value_fn"](entity)
                except Exception as exc:
                    _LOGGER.debug(
                        "Failed to set extra attribute %s for %s: %s",
                        description["name"],
                        self.entity_description.key,
                        str(exc),
                        exc_info=True,
                    )
                    extra_state_attributes[description["name"]] = None
            else:
                extra_state_attributes[description["name"]] = entity.value
        return extra_state_attributes

    def _set_up_unit_entities(self) -> None:
        """Back a temperature reported in both units by both, see _follow_temperature_unit."""
        entities = self._runtime_data.appliance.entities
        other_unit_entity = self.entity_description.other_unit_entity
        unit = getattr(self.entity_description, "native_unit_of_measurement", None)
        if (
            self._entity is None
            or other_unit_entity is None
            or other_unit_entity not in entities
            or TEMPERATURE_UNIT_ENTITY not in entities
        ):
            return
        if unit == UnitOfTemperature.CELSIUS:
            other_unit = UnitOfTemperature.FAHRENHEIT
        elif unit == UnitOfTemperature.FAHRENHEIT:
            other_unit = UnitOfTemperature.CELSIUS
        else:
            return
        self._unit_entities = {unit: self._entity, other_unit: entities[other_unit_entity]}
        self._temperature_unit_entity = entities[TEMPERATURE_UNIT_ENTITY]
        self._entities.extend((entities[other_unit_entity], self._temperature_unit_entity))
        self._follow_temperature_unit()

    def _follow_temperature_unit(self) -> None:
        """
        Read the temperature in the unit the appliance is set to.

        An appliance that reports a temperature in both units may only keep the
        one in its current unit up to date, so this follows its temperature unit
        setting. Home Assistant converts the shown value to its own unit either
        way. Keeps the current one while the appliance's unit is unknown.
        """
        if self._unit_entities is None or self._temperature_unit_entity is None:
            return
        unit = _APPLIANCE_TEMPERATURE_UNITS.get(str(self._temperature_unit_entity.value))
        if unit is None:
            return
        self._entity = self._unit_entities[unit]
        self._temperature_unit = unit

    def _set_up_alternate_entities(self) -> None:
        """Back a feature under several names by all of them, see _follow_alternate."""
        entities = self._runtime_data.appliance.entities
        names = self.entity_description.alternate_entities or ()
        alternates = [entities[name] for name in names if name in entities]
        if self._entity is None or not alternates:
            return
        self._alternates = [self._entity, *alternates]
        self._entities.extend(alternates)
        self._follow_alternate()

    def _follow_alternate(self) -> None:
        """
        Read and write the name the appliance currently offers.

        Some appliances offer one feature under different names in different
        programs (e.g. a washer's LaundryCare.Common.Option.SpeedPerfect and
        LaundryCare.Washer.Option.SpeedPerfect), marking the others Access.NONE.
        Keeps the current one while none is offered.
        """
        if self._alternates is None:
            return
        for entity in self._alternates:
            if entity.access not in (None, Access.NONE) and entity.available is not False:
                self._entity = entity
                return

    async def callback(self, _: HcEntity) -> None:
        self._follow_temperature_unit()
        self._follow_alternate()
        if not self._has_callback:
            self._has_callback = True
            try:
                self.async_write_ha_state()
            finally:
                self._has_callback = False
