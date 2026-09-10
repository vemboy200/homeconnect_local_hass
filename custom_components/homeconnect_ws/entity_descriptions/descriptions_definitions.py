"""Definitions for Entity Description."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict

from home_disconnect import HomeAppliance
from home_disconnect.entities import Access
from homeassistant.components.binary_sensor import BinarySensorEntityDescription
from homeassistant.components.button import ButtonEntityDescription
from homeassistant.components.fan import FanEntityDescription
from homeassistant.components.light import LightEntityDescription
from homeassistant.components.number import NumberEntityDescription
from homeassistant.components.select import SelectEntityDescription
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.components.update import UpdateEntityDescription
from homeassistant.helpers.entity import EntityDescription

if TYPE_CHECKING:
    from home_disconnect.entities import Entity as HcEntity
    from homeassistant.helpers.typing import StateType


class ExtraAttributeDict(TypedDict):
    """Dict for extra Attributes."""

    name: str
    entity: str
    value_fn: NotRequired[Callable[[HcEntity], StateType]]


class HCEntityDescription(EntityDescription, frozen_or_thawed=True):
    """Description for Base Entity."""

    entity: str | None = None
    entities: list[str] | None = None
    available_access: tuple[Access, ...] | None = None
    extra_attributes: list[ExtraAttributeDict] | None = None
    # For laundry appliances only: unlike appliance types that stay connected,
    # these never get to send the natural end-of-program update (remaining
    # time -> 0, progress -> 100%) that would otherwise settle these values -
    # the clean disconnect that freezes them is the same event that prevents
    # it. Clears to None instead of showing a stale in-progress-looking value
    # once coordinator.expected_offline is true.
    clear_on_expected_offline: bool = False


class HCSelectEntityDescription(
    HCEntityDescription, SelectEntityDescription, frozen_or_thawed=True
):
    """Description for Select Entity."""

    available_access: tuple[Access, ...] = (Access.READ_WRITE, Access.WRITE_ONLY)
    has_state_translation: bool = False
    mapping: dict[str, str] | None = None
    # A laundry appliance's own power-off write races its clean disconnect (see
    # HCEntity/coordinator.expected_offline) - the confirming update never
    # arrives before the socket closes, so the entity's last real value is
    # stuck at the pre-off state. Forces current_option to this value instead
    # of trusting that stale value, only while expected_offline is true.
    force_option_when_expected_offline: str | None = None


class HCSwitchEntityDescription(
    HCEntityDescription, SwitchEntityDescription, frozen_or_thawed=True
):
    """Description for Switch Entity."""

    value_mapping: tuple[str, str] | None = None
    available_access: tuple[Access, ...] = (Access.READ_WRITE, Access.WRITE_ONLY)
    # See HCSelectEntityDescription.force_option_when_expected_offline - same
    # race, but for the 2-state (on/off) power switch instead of the select.
    force_off_when_expected_offline: bool = False


class HCSensorEntityDescription(
    HCEntityDescription, SensorEntityDescription, frozen_or_thawed=True
):
    """Description for Sensor Entity."""

    available_access: tuple[Access, ...] = (Access.READ, Access.READ_WRITE)
    has_state_translation: bool = False
    # See HCSelectEntityDescription.force_option_when_expected_offline - same
    # race, but for a read-only enum sensor instead of the select.
    force_option_when_expected_offline: str | None = None
    mapping: dict[str, str] | None = None
    # Some appliances stop reporting an Option-based status (phase, progress)
    # once a program finishes instead of resetting it themselves - it stays
    # frozen on its last in-progress-looking value even though active_program
    # has already gone None and the appliance is powered off (confirmed live
    # on a Bosch dishwasher, issue #302: program_phase stuck on "Drying" at
    # 0% remaining time for as long as the appliance sat idle and off).
    # Forces this enum sensor to a specific value in that state instead -
    # only while both conditions hold, and only to a value this appliance's
    # own enum actually has (see force_option_when_expected_offline above).
    force_value_when_no_active_program: str | None = None
    # Same trigger as force_value_when_no_active_program, but for a sensor
    # with no sensible idle value of its own (e.g. program_progress) - goes
    # unavailable instead, matching how the Home Connect Cloud app itself
    # handles progress once there's nothing in progress.
    unavailable_when_no_active_program: bool = False


class HCBinarySensorEntityDescription(
    HCEntityDescription,
    BinarySensorEntityDescription,
    frozen_or_thawed=True,
):
    """Description for Binary Sensor Entity."""

    value_on: set[str] | None = None
    value_off: set[str] | None = None
    available_access: tuple[Access, ...] = (Access.READ, Access.READ_WRITE)


class HCButtonEntityDescription(
    HCEntityDescription, ButtonEntityDescription, frozen_or_thawed=True
):
    """Description for Button Entity."""

    available_access: tuple[Access, ...] = (Access.READ_WRITE, Access.WRITE_ONLY)


class HCNumberEntityDescription(
    HCEntityDescription, NumberEntityDescription, frozen_or_thawed=True
):
    """Description for Number Entity."""

    available_access: tuple[Access, ...] = (Access.READ_WRITE, Access.WRITE_ONLY)


class HCLightEntityDescription(HCEntityDescription, LightEntityDescription, frozen_or_thawed=True):
    """Description for Number Entity."""

    available_access: tuple[Access, ...] = (Access.READ_WRITE, Access.WRITE_ONLY)
    brightness_entity: str | None = None
    color_temperature_entity: str | None = None
    color_entity: str | None = None
    color_mode_entity: str | None = None


class HCFanEntityDescription(HCEntityDescription, FanEntityDescription, frozen_or_thawed=True):
    """Description for Fan Entity."""

    available_access: tuple[Access, ...] = (Access.READ_WRITE,)
    default_program: str | None = None


class HCUpdateEntityDescription(
    HCEntityDescription, UpdateEntityDescription, frozen_or_thawed=True
):
    """Description for Update Entity."""

    available_access: tuple[Access, ...] = (Access.READ, Access.READ_WRITE)
    command_entity: str | None = None


class EntityDescriptions(TypedDict, total=False):
    """Entity descriptions by type; a "dynamic" generator fills in only the relevant keys."""

    button: list[HCButtonEntityDescription]
    active_program: list[HCSensorEntityDescription]
    binary_sensor: list[HCBinarySensorEntityDescription]
    event_sensor: list[HCSensorEntityDescription]
    number: list[HCNumberEntityDescription]
    program: list[HCSelectEntityDescription]
    select: list[HCSelectEntityDescription]
    sensor: list[HCSensorEntityDescription]
    start_button: list[HCButtonEntityDescription]
    switch: list[HCSwitchEntityDescription]
    wifi: list[HCSensorEntityDescription]
    light: list[HCLightEntityDescription]
    fan: list[HCFanEntityDescription]
    update: list[HCUpdateEntityDescription]


_EntityDescriptionsDefinitionsType = dict[
    Literal[
        "button",
        "active_program",
        "binary_sensor",
        "event_sensor",
        "number",
        "program",
        "select",
        "sensor",
        "start_button",
        "switch",
        "wifi",
        "light",
        "fan",
        "update",
        "dynamic",
    ],
    list[
        HCEntityDescription
        | Callable[[HomeAppliance], HCEntityDescription | EntityDescriptions | None]
    ],
]

_EntityDescriptionsType = dict[
    Literal[
        "button",
        "active_program",
        "binary_sensor",
        "event_sensor",
        "number",
        "program",
        "select",
        "sensor",
        "start_button",
        "switch",
        "wifi",
        "light",
        "fan",
        "update",
    ],
    list[HCEntityDescription],
]
