"""Definitions for Entity Description."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Container, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict

from home_disconnect import Appliance
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
    # The same temperature in the other unit (Celsius or Fahrenheit), for an
    # appliance that reports both. The entity follows the appliance's own
    # temperature unit setting between the two, see HCEntity.
    other_unit_entity: str | None = None
    # The same feature under other names, which some appliances offer instead
    # of entity depending on the program. The entity follows whichever the
    # appliance currently offers, see HCEntity.
    alternate_entities: tuple[str, ...] | None = None


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
    # The values that show as on; any other value shows as off. Without it, a
    # value that's neither side of value_mapping shows as unknown. For power
    # state, whose list of states is longer than the two the switch sets.
    on_values: tuple[str, ...] | None = None
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
    mapping: dict[str, str] | None = None
    # Some appliances stop reporting an Option-based status (phase, progress)
    # once a program finishes instead of resetting it themselves - it stays
    # frozen on its last in-progress-looking value even though active_program
    # has already gone None and the appliance is powered off (confirmed live
    # on a Bosch dishwasher, issue #302: program_phase stuck on "Drying" at
    # 0% remaining time for as long as the appliance sat idle and off).
    # Forces this enum sensor to a specific value in that state instead -
    # only while both conditions hold, and only to a value this appliance's
    # own enum actually has (see HCSelectEntityDescription.force_option_when_expected_offline).
    force_value_when_no_active_program: str | None = None
    # Same trigger as force_value_when_no_active_program, but for a sensor
    # with no sensible idle value of its own (e.g. program_progress) - goes
    # unavailable instead, matching how the Home Connect Cloud app itself
    # handles progress once there's nothing in progress.
    unavailable_when_no_active_program: bool = False
    # Some appliances flag an Option unavailable while still counting it: a
    # Thermador PRG486WDH oven running a heating mode with no timer set
    # reports ElapsedProgramTime as available=false while its value keeps
    # going up. Shows the value anyway while a program is active (and there
    # is a value), falling back to the appliance's own flag otherwise.
    available_while_program_active: bool = False
    # Same, but only while RemainingProgramTime is also available with a value, since
    # these only mean something for a program with an end. A dryer flags ProgramProgress
    # unavailable while counting it (fork issue #206); an oven with no timer set reports
    # progress stuck at 100% and no remaining time.
    available_with_remaining_time: bool = False
    # Converts the appliance's value before it's shown, for a unit HA's
    # device class doesn't accept (water in mL) or a value that means
    # "not measured yet".
    value_fn: Callable[[StateType], StateType] | None = None


def keep_known_events(
    description: HCSensorEntityDescription, appliance_entities: Container[str]
) -> HCSensorEntityDescription | None:
    """
    Reduce an event sensor to the events this appliance actually has.

    An event sensor lists several stages of one thing (e.g. descaling due,
    overdue, blocked), and not every model has every stage. Instead of
    dropping the whole sensor when one is missing, keep the ones the
    appliance knows together with their options; the last option is the
    fallback when none is set and always stays.
    """
    events = description.entities or []
    known = [index for index, event in enumerate(events) if event in appliance_entities]
    if not known:
        return None
    if len(known) == len(events):
        return description
    options = description.options
    if options is not None:
        options = [options[index] for index in known] + [options[-1]]
    return replace(description, entities=[events[index] for index in known], options=options)


class HCBinarySensorEntityDescription(
    HCEntityDescription,
    BinarySensorEntityDescription,
    frozen_or_thawed=True,
):
    """Description for Binary Sensor Entity."""

    value_on: set[str] | None = None
    value_off: set[str] | None = None
    available_access: tuple[Access, ...] = (Access.READ, Access.READ_WRITE)
    # Problem sensors only: whether the appliance's Problem sensor counts this one
    in_problem_sensor: bool = True


class HCButtonEntityDescription(
    HCEntityDescription, ButtonEntityDescription, frozen_or_thawed=True
):
    """Description for Button Entity."""

    available_access: tuple[Access, ...] = (Access.READ_WRITE, Access.WRITE_ONLY)
    # A button writes True to its Command by default. A button backed by a
    # Setting instead does its own write here, through a library method (e.g.
    # setting the clock to the current time).
    press_fn: Callable[[Appliance], Awaitable[None]] | None = None


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


class HCUpdateEntityDescription(
    HCEntityDescription, UpdateEntityDescription, frozen_or_thawed=True
):
    """Description for Update Entity."""

    available_access: tuple[Access, ...] = (Access.READ, Access.READ_WRITE)
    command_entity: str | None = None


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
        "delay_start",
        "switch",
        "wifi",
        "ipv4",
        "ipv6",
        "light",
        "fan",
        "update",
    ],
    list[
        HCEntityDescription
        | Callable[[Appliance], HCEntityDescription | Sequence[HCEntityDescription] | None]
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
        "delay_start",
        "switch",
        "wifi",
        "ipv4",
        "ipv6",
        "light",
        "fan",
        "update",
    ],
    list[HCEntityDescription],
]
