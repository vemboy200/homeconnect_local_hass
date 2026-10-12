"""Helper functions."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from home_disconnect.entities import Access, Option, SelectedProgram, Setting
from home_disconnect.errors import AccessError, CodeResponsError, NotConnectedError
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.service import async_extract_config_entry_ids

from .const import DOMAIN

if TYPE_CHECKING:
    import re
    from collections.abc import Callable, Coroutine, Iterator

    from home_disconnect import HomeAppliance
    from home_disconnect.entities import Entity as HcEntity
    from home_disconnect.entities import Program
    from homeassistant.core import HomeAssistant, ServiceCall

    from . import HCConfigEntry, HCData
    from .entity import HCEntity

_LOGGER = logging.getLogger(__name__)


def create_entities(
    entities_classes: dict[str, type[HCEntity]], runtime_data: HCData
) -> set[HCEntity]:
    """Create entities from entity_descriptions."""
    entities = set()
    for entity_key, entity_class in entities_classes.items():
        if entity_key in runtime_data.available_entity_descriptions:
            for entity_description in runtime_data.available_entity_descriptions[entity_key]:
                _LOGGER.debug("Creating Entity %s", entity_description.key)
                try:
                    entity = entity_class(
                        entity_description=entity_description, runtime_data=runtime_data
                    )
                except Exception:
                    _LOGGER.exception("Failed to create Entity %s", entity_description.key)
                else:
                    entities.add(entity)
    return entities


def merge_dicts[K, V](*args: dict[K, list[V]]) -> dict[K, list[V]]:
    """Merge multiple dictionaries of type dict[str, list]."""
    out_dict: dict[K, list[V]] = {}
    for in_dict in args:
        for key, value in in_dict.items():
            if key not in out_dict:
                out_dict[key] = value
            else:
                out_dict[key].extend(value)
    return out_dict


@dataclass
class EntityMatch:
    """Returned by get_entities_from_regex."""

    entity: str
    groups: tuple[str, ...]


def get_entities_from_regex(
    appliance: HomeAppliance, pattern: re.Pattern[str]
) -> list[EntityMatch]:
    """Get all entities matching the pattern."""
    return [
        EntityMatch(entity=entity, groups=match.groups())
        for entity in appliance.entities
        if (match := pattern.match(entity))
    ]


def get_groups_from_regex(
    appliance: HomeAppliance, pattern: re.Pattern[str]
) -> set[tuple[str, ...]]:
    """Get all regex groups matching the pattern."""
    groups: set[tuple[str, ...]] = set()
    for entity in appliance.entities:
        if (match := pattern.match(entity)) and match.groups() not in groups:
            groups.add(match.groups())
    return groups


async def get_config_entry_from_call(
    hass: HomeAssistant, service_call: ServiceCall
) -> HCConfigEntry:
    """Get the config entry from a service call."""
    config_entry_ids = await async_extract_config_entry_ids(service_call)
    for config_entry_id in config_entry_ids:
        config_entry = hass.config_entries.async_get_entry(config_entry_id)
        if config_entry is not None and config_entry.domain == DOMAIN:
            return config_entry
    raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_appliance")


def entity_is_available(
    entity: HcEntity | None, available_access: tuple[Access, ...] | None
) -> bool:
    """Check is HC entity is available."""
    available = True
    if entity is not None and hasattr(entity, "available"):
        available &= entity.available

    if entity is not None and available_access is not None and hasattr(entity, "access"):
        available &= entity.access in available_access
    return available


_LOCKABLE_ENTITY_TYPES = (Option, Setting, SelectedProgram)


def is_lockable(entity: HcEntity | None) -> bool:
    """Whether entity is a type HC locks read-only rather than hides, regardless of access."""
    return isinstance(entity, _LOCKABLE_ENTITY_TYPES)


def is_locked(entity: HcEntity | None) -> bool:
    """
    Whether entity is currently locked read-only, not just inapplicable.

    Options (e.g. an iDos dosing switch while a program runs),
    SelectedProgram (e.g. while a delayed start is armed - confirmed live on
    fork issue #59 via a Bosch WGB244A0BY's own debug log, access flips
    READ_WRITE -> READ the moment the delay is armed and back once the wash
    actually starts) and Settings (e.g. a Bosch WQB245A0BY dryer's
    CupboardDryFineAdjust/IronDryFineAdjust, READ for the whole ~1h47m of a
    running program and READ_WRITE again once it ends, from the same issue)
    are the HC entity types whose write access depends on appliance state
    this way - Home Connect itself shows these as visible-but-disabled on the
    appliance's own panel/app rather than hiding them. Access.READ
    specifically means "still readable, just not writable right now" -
    Access.NONE means "not applicable at all", which should stay genuinely
    unavailable rather than shown as read-only.
    """
    return isinstance(entity, _LOCKABLE_ENTITY_TYPES) and entity.access == Access.READ


def ensure_writable(entity: HcEntity | None) -> None:
    """Raise a clear error instead of silently attempting a write a locked entity will reject."""
    if is_locked(entity):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="read_only",
        )


def needs_full_option_set(program: Program) -> bool:
    """
    Whether this appliance expects program and options as one complete write.

    Appliance-wide: Program.full_option_set falls back to the appliance value,
    which is true as soon as *either* SelectedProgram or ActiveProgram declares
    the flag. Right for the ActiveProgram writes (start button, fan) - for a
    SelectedProgram write use selected_program_needs_full_option_set().
    """
    return program.full_option_set


def selected_program_needs_full_option_set(entity: SelectedProgram) -> bool:
    """
    Whether a write to SelectedProgram itself has to carry the complete option set.

    A device description declares fullOptionSet per resource, and the two can
    disagree: a Siemens EQ.9 CoffeeMaker has

        <selectedProgram fullOptionSet="false" access="readwrite" />
        <activeProgram   fullOptionSet="true"  access="read" />

    so selecting a program there is an ordinary SelectedProgram write, while
    the appliance-wide value says otherwise. Ask the entity being written to,
    not the appliance.
    """
    return entity.full_option_set


def is_unplugged_probe(appliance: HomeAppliance, option: Option) -> bool:
    """
    Whether option is a meat probe setpoint while no probe is plugged in.

    Supplying it anyway makes the appliance reject the entire program write.
    """
    if "MeatProbeTemperature" not in option.name:
        return False
    plugged = appliance.status.get("Cooking.Oven.Status.MeatprobePlugged")
    return not bool(getattr(plugged, "value", False))


def _writable_options(appliance: HomeAppliance, program: Program) -> Iterator[Option]:
    """
    Yield the program's options that may go into a program write right now.

    Skips read-only options, an unplugged meat probe, and options the appliance
    does not offer for this program at the moment (available is False): a
    Siemens EQ.9 CoffeeMaker lists DisplayName on every beverage program but
    never reports it or makes it available, and sending any value for it makes
    the appliance reject the whole write with 400 - the same effect the
    meat-probe special case guards against, just for the general case.
    """
    for opt in program._options:  # noqa: SLF001
        if opt.access != Access.READ_WRITE:
            continue
        if is_unplugged_probe(appliance, opt):
            continue
        if opt.available is False:
            continue
        yield opt


def build_known_option_set(
    appliance: HomeAppliance, program: Program
) -> dict[int, str | int | bool]:
    """
    Collect the options whose value the appliance has reported, for a program write.

    Mirrors the library's default merge (every READ_WRITE option's value_shadow)
    so that known values still go out - a hood's Venting program needs its real
    level to start - but leaves out options that have no value yet. The library
    would send those as {"uid": x, "value": None}, and an appliance that never
    reported the option rejects the whole write with 400.
    """
    options: dict[int, str | int | bool] = {}
    for opt in _writable_options(appliance, program):
        value = opt.value_shadow
        if value is None:
            value = opt.value
        if value is None:
            continue
        options[opt.uid] = value
    return options


def build_full_option_set(
    appliance: HomeAppliance, program: Program
) -> dict[int, str | int | bool]:
    """
    Collect a complete, well-formed option set for a program write.

    An appliance that wants a full option set rejects {"uid": x, "value": None}
    entries, so on top of the known values fall back to the option's minimum.
    Options that stay valueless even then are left out rather than sent as null.
    """
    options = build_known_option_set(appliance, program)
    for opt in _writable_options(appliance, program):
        if opt.uid in options or opt.min is None:
            continue
        # opt.min is typed float (generic XML min/max parsing), but the
        # wire protocol only ever takes int/str/bool option values.
        options[opt.uid] = int(opt.min)
    return options


def error_decorator[T](
    func: Callable[..., Coroutine[Any, Any, T]],
) -> Callable[..., Coroutine[Any, Any, T]]:
    """Catches HomeConnect Errors and raise HomeAssistantError."""

    async def wrap(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except AccessError:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="access_error",
            ) from None
        except CodeResponsError as exc:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="code_respons",
                translation_placeholders={"message": exc.message},
            ) from None
        except NotConnectedError:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="not_connected",
            ) from None
        except TimeoutError:
            # send_sync waits on a response queue that stays empty when the
            # appliance never answers a message (an action it does not
            # implement, or a connection that dropped mid-request). Without
            # this the bare asyncio TimeoutError reaches the frontend as an
            # opaque "unknown error".
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_timeout",
            ) from None

    return wrap


START_IN_RELATIVE = "BSH.Common.Option.StartInRelative"
FINISH_IN_RELATIVE = "BSH.Common.Option.FinishInRelative"
ESTIMATED_TOTAL_PROGRAM_TIME = "BSH.Common.Option.EstimatedTotalProgramTime"
DELAY_START_NONE = "no_delay"
DELAY_START_OPTIONS = [DELAY_START_NONE, *(f"{hours}h" for hours in range(1, 25))]


@dataclass
class DelayStart:
    """
    The start delay picked in the "Delay start" select, held in HA.

    The appliance has no notion of this value on its own: it only accepts
    StartInRelative/FinishInRelative as an option of the program start
    (#146), so the select keeps the choice here and the Start button turns
    it into that option when the program is started.
    """

    option: str = DELAY_START_NONE
    _listeners: list[Callable[[], None]] = field(default_factory=list)

    @property
    def seconds(self) -> int:
        """Return the selected delay in seconds, 0 for no delay."""
        if self.option == DELAY_START_NONE:
            return 0
        return int(self.option.removesuffix("h")) * 3600

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Call listener whenever the delay is reset; returns a remove function."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def reset(self) -> None:
        """Back to no delay after a successful start, like the official app."""
        self.option = DELAY_START_NONE
        for listener in list(self._listeners):
            listener()


def delay_start_entity(appliance: HomeAppliance) -> HcEntity | None:
    """
    Return the option the delay goes into: StartInRelative, else FinishInRelative.

    StartInRelative takes the delay as-is; FinishInRelative needs the program
    duration added, so prefer the simpler one when an appliance has both.
    """
    return appliance.entities.get(START_IN_RELATIVE) or appliance.entities.get(FINISH_IN_RELATIVE)


def _program_duration(
    appliance: HomeAppliance, finish_in: HcEntity, options: dict[int, Any]
) -> int:
    """
    Return the selected program's duration in seconds.

    EstimatedTotalProgramTime first: FinishInRelative may already hold a
    finish time someone set through the "Finish in" number on an appliance
    that accepts that write, and adding the delay on top would count it
    twice. With a program selected, the Siemens WM16XKH2EU washer reports
    both as the program duration (3600 s for the same program, #146), so
    FinishInRelative stays as the fallback for appliances without
    EstimatedTotalProgramTime.
    """
    for source in (appliance.entities.get(ESTIMATED_TOTAL_PROGRAM_TIME), finish_in):
        if source is None or not getattr(source, "available", True):
            continue
        duration = options.get(source.uid, source.value)
        if duration is not None:
            return int(duration)
    raise HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="delay_start_duration_unknown",
    )


def apply_delay_start(
    appliance: HomeAppliance, delay_start: DelayStart, options: dict[int, Any]
) -> dict[int, Any]:
    """
    Add the selected start delay to the program start options.

    StartInRelative gets the delay itself. FinishInRelative gets the program
    duration plus the delay (see _program_duration for where it comes from).
    """
    seconds = delay_start.seconds
    if not seconds:
        return options
    entity = delay_start_entity(appliance)
    if entity is None:
        return options
    if entity.name == START_IN_RELATIVE:
        value = seconds
    else:
        value = _program_duration(appliance, entity, options) + seconds
    max_value = getattr(entity, "max", None)
    if max_value is not None and value > max_value:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="delay_start_too_long",
            translation_placeholders={"max_hours": str(int(max_value) // 3600)},
        )
    return {**options, entity.uid: value}
