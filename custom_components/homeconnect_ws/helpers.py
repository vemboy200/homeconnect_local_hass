"""Helper functions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from home_disconnect.entities import Access, Option, SelectedProgram
from home_disconnect.errors import AccessError, CodeResponsError, NotConnectedError
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.service import async_extract_config_entry_ids

from .const import DOMAIN

if TYPE_CHECKING:
    import re
    from collections.abc import Callable, Coroutine

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


_LOCKABLE_ENTITY_TYPES = (Option, SelectedProgram)


def is_lockable(entity: HcEntity | None) -> bool:
    """Whether entity is a type HC locks read-only rather than hides, regardless of access."""
    return isinstance(entity, _LOCKABLE_ENTITY_TYPES)


def is_locked(entity: HcEntity | None) -> bool:
    """
    Whether entity is currently locked read-only, not just inapplicable.

    Options (e.g. an iDos dosing switch while a program runs) and
    SelectedProgram (e.g. while a delayed start is armed - confirmed live on
    fork issue #59 via a Bosch WGB244A0BY's own debug log, access flips
    READ_WRITE -> READ the moment the delay is armed and back once the wash
    actually starts) are the two HC entity types whose write access depends
    on appliance state this way - Home Connect itself shows these as
    visible-but-disabled on the appliance's own panel/app rather than hiding
    them. Access.READ specifically means "still readable, just not writable
    right now" - Access.NONE means "not applicable at all", which should stay
    genuinely unavailable rather than shown as read-only.
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
    """Whether this appliance expects program and options as one complete write."""
    return program.full_option_set


def is_unplugged_probe(appliance: HomeAppliance, option: Option) -> bool:
    """
    Whether option is a meat probe setpoint while no probe is plugged in.

    Supplying it anyway makes the appliance reject the entire program write.
    """
    if "MeatProbeTemperature" not in option.name:
        return False
    plugged = appliance.status.get("Cooking.Oven.Status.MeatprobePlugged")
    return not bool(getattr(plugged, "value", False))


def build_full_option_set(
    appliance: HomeAppliance, program: Program
) -> dict[int, str | int | bool]:
    """
    Collect a complete, well-formed option set for a program write.

    The library derives the option list from each option's value_shadow, which
    stays None until the appliance has reported a value. An appliance that wants
    a full option set rejects the resulting {"uid": x, "value": None} entries, so
    fall back to the current value and finally to the option's minimum. Options
    that stay valueless even then are left out rather than sent as null.
    """
    options: dict[int, str | int | bool] = {}
    for opt in program._options:  # noqa: SLF001
        if opt.access != Access.READ_WRITE:
            continue
        if is_unplugged_probe(appliance, opt):
            continue
        value = opt.value_shadow
        if value is None:
            value = opt.value
        if value is None and opt.min is not None:
            # opt.min is typed float (generic XML min/max parsing), but the
            # wire protocol only ever takes int/str/bool option values.
            value = int(opt.min)
        if value is None:
            continue
        options[opt.uid] = value
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
