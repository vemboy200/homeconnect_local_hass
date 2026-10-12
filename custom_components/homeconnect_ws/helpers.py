"""Helper functions."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from home_disconnect import (
    Access,
    AccessError,
    ConnectionClosedError,
    InvalidValueError,
    ResponseError,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.service import async_extract_config_entry_ids

from .const import DOMAIN

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from home_disconnect import Appliance
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
        # READ_STATIC is read-only and fixed (e.g. an oven cavity's size): wherever READ
        # counts as available, so does READ_STATIC.
        if entity.access == Access.READ_STATIC:
            available &= Access.READ in available_access
        else:
            available &= entity.access in available_access
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


def remote_start_error(runtime_data: HCData) -> HomeAssistantError:
    """Return the error for a start the appliance refuses because remote start is off."""
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="remote_start_not_allowed",
        translation_placeholders={
            "device_name": runtime_data.device_info.get("name") or "your appliance"
        },
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


START_IN_RELATIVE = "BSH.Common.Option.StartInRelative"
FINISH_IN_RELATIVE = "BSH.Common.Option.FinishInRelative"
DELAY_START_NONE = "no_delay"
DELAY_START_OPTIONS = [DELAY_START_NONE, *(f"{hours}h" for hours in range(1, 25))]


@dataclass
class DelayStart:
    """
    The start delay picked in the "Delay start" select, held in HA.

    The appliance has no notion of this value on its own: it only accepts
    StartInRelative/FinishInRelative as an option of the program start
    (#146), so the select keeps the choice here and the Start button passes
    it to Appliance.start_program(), which turns it into that option.
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


def delay_start_entity(appliance: Appliance) -> HcEntity | None:
    """
    Return the option the delay goes into: StartInRelative, else FinishInRelative.

    StartInRelative takes the delay as-is; FinishInRelative needs the program
    duration added, so prefer the simpler one when an appliance has both.
    """
    return appliance.entities.get(START_IN_RELATIVE) or appliance.entities.get(FINISH_IN_RELATIVE)
