"""Helper functions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from home_disconnect import (
    AccessError,
    ConnectionClosedError,
    InvalidValueError,
    ResponseError,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.service import async_extract_config_entry_ids

from .const import DOMAIN

if TYPE_CHECKING:
    import re
    from collections.abc import Callable, Coroutine

    from home_disconnect import Access, Appliance
    from home_disconnect import Entity as HcEntity
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


def get_entities_from_regex(appliance: Appliance, pattern: re.Pattern[str]) -> list[EntityMatch]:
    """Get all entities matching the pattern."""
    return [
        EntityMatch(entity=entity, groups=match.groups())
        for entity in appliance.entities
        if (match := pattern.match(entity))
    ]


def get_groups_from_regex(appliance: Appliance, pattern: re.Pattern[str]) -> set[tuple[str, ...]]:
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
        # None (not reported yet) counts as available.
        available &= entity.available is not False

    if entity is not None and available_access is not None and hasattr(entity, "access"):
        access = entity.access
        # readStatic is read-only and fixed (e.g. an oven cavity's size): wherever
        # READ counts as available, so does READ_STATIC.
        if access is not None and access.value == "readstatic":
            available &= any(a.value == "read" for a in available_access)
        else:
            available &= access in available_access
    return available


def is_lockable(entity: HcEntity | None) -> bool:
    """Whether entity is a type HC locks read-only rather than hides, regardless of access."""
    return entity is not None and entity.lockable


def is_locked(entity: HcEntity | None) -> bool:
    """
    Whether entity is currently locked read-only, not just inapplicable.

    Options (e.g. an iDos dosing switch while a program runs),
    SelectedProgram (e.g. while a delayed start is armed - fork issue #59) and
    Settings (e.g. a dryer's fine-adjust settings during a program) are
    locked READ rather than hidden - the library's Entity.locked. Access.NONE
    means "not applicable at all" and stays unavailable instead.
    """
    return entity is not None and entity.locked


def ensure_writable(entity: HcEntity | None) -> None:
    """Raise a clear error instead of silently attempting a write a locked entity will reject."""
    if is_locked(entity):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="read_only",
        )


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
        except InvalidValueError as exc:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="code_respons",
                translation_placeholders={"message": str(exc)},
            ) from None
        except ResponseError as exc:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="code_respons",
                translation_placeholders={"message": str(exc)},
            ) from None
        except ConnectionClosedError:
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
