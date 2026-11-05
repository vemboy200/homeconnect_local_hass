"""Number entities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.number import (
    DEFAULT_MAX_VALUE,
    DEFAULT_MIN_VALUE,
    NumberEntity,
    RestoreNumber,
)

from .entity import HCEntity
from .helpers import create_entities, ensure_writable, error_decorator

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import HCConfigEntry, HCData
    from .entity_descriptions.descriptions_definitions import HCNumberEntityDescription

PARALLEL_UPDATES = 0

# The longest delay when the appliance doesn't report a maximum, in minutes: 24 hours, like
# the Delay start select before 2.0 and the Home Connect app.
DELAY_START_FALLBACK_MAX = 24 * 60


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    config_entry: HCConfigEntry,
    async_add_entites: AddEntitiesCallback,
) -> None:
    """Set up number platform."""
    entities = create_entities(
        {"number": HCNumber, "delay_start": HCDelayStartNumber}, config_entry.runtime_data
    )
    async_add_entites(entities)


class HCNumber(HCEntity, NumberEntity):
    """Number Entity."""

    entity_description: HCNumberEntityDescription

    def __init__(
        self,
        entity_description: HCNumberEntityDescription,
        runtime_data: HCData,
    ) -> None:
        super().__init__(entity_description, runtime_data)

    @property
    def native_value(self) -> int | float | None:
        if self.entity_description.clear_on_expected_offline and (
            self._runtime_data.coordinator.expected_offline
        ):
            return None
        if self._entity is None:
            return None
        value = self._entity.value
        return value if isinstance(value, int | float) and not isinstance(value, bool) else None

    @property
    def native_unit_of_measurement(self) -> str | None:
        return self._temperature_unit or super().native_unit_of_measurement

    @property
    def native_min_value(self) -> float:
        if (
            self._entity is not None
            and hasattr(self._entity, "min")
            and self._entity.min is not None
        ):
            return float(self._entity.min)
        if self.entity_description.native_min_value is not None:
            return self.entity_description.native_min_value
        return DEFAULT_MIN_VALUE

    @property
    def native_max_value(self) -> float:
        if (
            self._entity is not None
            and hasattr(self._entity, "max")
            and self._entity.max is not None
        ):
            return float(self._entity.max)
        if self.entity_description.native_max_value is not None:
            return self.entity_description.native_max_value
        return DEFAULT_MAX_VALUE

    @property
    def native_step(self) -> float | None:
        if (step_for_brands := self.entity_description.step_for_brands) is not None:
            step, brands = step_for_brands
            if self._runtime_data.appliance.info.get("brand", "").upper() in brands:
                return step
        if (
            self._entity is not None
            and hasattr(self._entity, "step")
            and self._entity.step is not None
        ):
            return float(self._entity.step)
        return None

    @error_decorator
    async def async_set_native_value(self, value: float) -> None:
        if self._entity is not None:
            ensure_writable(self._entity)
            await self._entity.set_value(int(value))


class HCDelayStartNumber(HCEntity, RestoreNumber):
    """
    "Delay start" number: how long after Start the program starts, in minutes.

    The value is held in HA (and restored after a restart), not written to the
    appliance: some appliances only accept StartInRelative/FinishInRelative as
    an option of the program start (#146). The Start button applies it, as
    StartInRelative or as FinishInRelative = program duration + delay, and
    resets it to 0 after a successful start.
    """

    entity_description: HCNumberEntityDescription
    _show_when_locked = False
    _remove_reset_listener: Callable[[], None] | None = None

    @property
    def available(self) -> bool:
        # Not tied to the backing option's own availability: StartIn/FinishIn
        # is often withdrawn until a program is selected, but setting the
        # delay first and the program second must work.
        return (
            self._runtime_data.appliance.connected
            or self._runtime_data.coordinator.expected_offline
        )

    @property
    def native_value(self) -> float:
        return self._runtime_data.delay_start.seconds / 60

    @property
    def native_max_value(self) -> float:
        # The option's own maximum. For FinishInRelative that's the latest finish, so the
        # longest delay is a bit shorter; the Start button says so if it's too long.
        if self._entity is not None and getattr(self._entity, "max", None) is not None:
            return float(self._entity.max) / 60
        return DELAY_START_FALLBACK_MAX

    @property
    def native_step(self) -> float | None:
        if self._entity is not None and getattr(self._entity, "step", None):
            return float(self._entity.step) / 60
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {}

    async def async_set_native_value(self, value: float) -> None:
        self._runtime_data.delay_start.seconds = round(value * 60)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_data = await self.async_get_last_number_data()
        if last_data is not None and last_data.native_value is not None:
            self._runtime_data.delay_start.seconds = round(last_data.native_value * 60)
        self._remove_reset_listener = self._runtime_data.delay_start.add_listener(
            self.async_write_ha_state
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_reset_listener is not None:
            self._remove_reset_listener()
            self._remove_reset_listener = None
        await super().async_will_remove_from_hass()
