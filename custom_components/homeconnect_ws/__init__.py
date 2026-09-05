"""The Home Connect Websocket integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Never

import voluptuous as vol
from home_disconnect import CodeResponsError, Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DESCRIPTION, CONF_HOST, EVENT_HOMEASSISTANT_STOP
from homeassistant.exceptions import ConfigEntryError, ServiceValidationError
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.util.hass_dict import HassKey

from .const import (
    CONF_APPLIANCE_INFO,
    CONF_DESCRIPTION_FILENAME,
    CONF_DEV_OVERRIDE_HOST,
    CONF_DEV_OVERRIDE_PSK,
    CONF_DEV_SETUP_FROM_DUMP,
    CONF_FEATURE_FILENAME,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import HomeConnectCoordinator
from .entity_descriptions import get_available_entities
from .export_view import HCExportView
from .helpers import error_decorator, get_config_entry_from_call
from .profile_storage import load_description_files, remove_description_files

if TYPE_CHECKING:
    from home_disconnect import HomeAppliance
    from homeassistant.core import Event, HomeAssistant, ServiceCall, ServiceResponse
    from homeassistant.helpers.typing import ConfigType

    from .entity_descriptions import _EntityDescriptionsType

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: {
            vol.Optional(CONF_DEV_SETUP_FROM_DUMP, default=False): vol.Boolean(),
            vol.Optional(CONF_DEV_OVERRIDE_HOST): str,
            vol.Optional(CONF_DEV_OVERRIDE_PSK): str,
        }
    },
    extra=vol.ALLOW_EXTRA,
)


@dataclass
class HCData:
    """Dataclass for runtime data."""

    appliance: HomeAppliance
    device_info: DeviceInfo
    available_entity_descriptions: _EntityDescriptionsType
    coordinator: HomeConnectCoordinator


@dataclass
class HCConfig:
    """Dataclass for hass.data."""

    setup_from_dump: bool = False
    override_host: str | None = None
    override_psk: str | None = None


type HCConfigEntry = ConfigEntry[HCData]

HC_KEY: HassKey[HCConfig] = HassKey(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up integration global config."""
    hass.data.setdefault(DOMAIN, HCConfig())
    if hass.http is not None:
        hass.http.register_view(HCExportView())
    if DOMAIN in config:
        hass.data[HC_KEY].setup_from_dump = config[DOMAIN].get(CONF_DEV_SETUP_FROM_DUMP, False)
        hass.data[HC_KEY].override_host = config[DOMAIN].get(CONF_DEV_OVERRIDE_HOST)
        hass.data[HC_KEY].override_psk = config[DOMAIN].get(CONF_DEV_OVERRIDE_PSK)

    def _get_entity_or_raise(appliance: HomeAppliance, key: str, error_key: str) -> Entity:
        entity = appliance.entities.get(key)
        if not entity:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key=error_key,
            )
        return entity

    def _duration_to_seconds(data: dict[str, Any]) -> int:
        return (
            int(data.get("hours", 0)) * 3600
            + int(data.get("minutes", 0)) * 60
            + int(data.get("seconds", 0))
        )

    def _raise_start_error(err: CodeResponsError) -> Never:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="start_program_error",
            translation_placeholders={"code": str(err.code), "resource": err.resource},
        ) from None

    async def _set_value_or_raise(entity: Entity, relative_time_in_seconds: int) -> None:
        try:
            await entity.set_value(relative_time_in_seconds)
        except CodeResponsError as exc:
            _raise_start_error(exc)

    @error_decorator
    async def handle_start_program(call: ServiceCall) -> ServiceResponse:
        config_entry = await get_config_entry_from_call(hass, call)

        options: dict[int, str | int | bool] = {}
        appliance = config_entry.runtime_data.appliance
        if "start_in" in call.data:
            entity = _get_entity_or_raise(
                appliance, "BSH.Common.Option.StartInRelative", "start_in_not_available"
            )
            options[entity.uid] = _duration_to_seconds(call.data["start_in"])

        if "finish_in" in call.data:
            entity = _get_entity_or_raise(
                appliance, "BSH.Common.Option.FinishInRelative", "finish_in_not_available"
            )
            options[entity.uid] = _duration_to_seconds(call.data["finish_in"])

        if appliance.selected_program:
            try:
                await appliance.selected_program.start(options)
            except CodeResponsError as exc:
                _raise_start_error(exc)
        else:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_program_selected",
            )
        return None

    @error_decorator
    async def handle_set_start_in(call: ServiceCall) -> ServiceResponse:
        config_entry = await get_config_entry_from_call(hass, call)
        appliance = config_entry.runtime_data.appliance
        await _set_value_or_raise(
            _get_entity_or_raise(
                appliance, "BSH.Common.Option.StartInRelative", "start_in_not_available"
            ),
            _duration_to_seconds(call.data["start_in"]),
        )
        return None

    @error_decorator
    async def handle_set_finish_in(call: ServiceCall) -> ServiceResponse:
        config_entry = await get_config_entry_from_call(hass, call)
        appliance = config_entry.runtime_data.appliance
        await _set_value_or_raise(
            _get_entity_or_raise(
                appliance, "BSH.Common.Option.FinishInRelative", "finish_in_not_available"
            ),
            _duration_to_seconds(call.data["finish_in"]),
        )
        return None

    hass.services.async_register(DOMAIN, "start_program", handle_start_program)
    hass.services.async_register(DOMAIN, "set_start_in", handle_set_start_in)
    hass.services.async_register(DOMAIN, "set_finish_in", handle_set_finish_in)
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: HCConfigEntry,
) -> bool:
    """Set up this integration using config entry."""
    new_data = None
    if CONF_DESCRIPTION not in config_entry.data:
        # A v2-shaped entry (upstream chris-mc1/homeconnect_local_hass, or a
        # previous run of this fork's own v1<->v2 conversion elsewhere) -
        # this fork only ever speaks the older, simpler CONF_DESCRIPTION
        # shape, so convert it down once rather than teaching the rest of
        # the integration to understand two schemas. Triggered by data
        # shape, not entry.version: HA hard-blocks setup entirely (before
        # any of our code runs) if entry.version is higher than this
        # integration's declared VERSION, so this can't be done as a
        # migration step - it has to happen here, every time, cheaply
        # short-circuited by the CONF_DESCRIPTION check above once an entry
        # has been converted.
        description = await load_description_files(hass, config_entry)
        new_data = {
            k: v
            for k, v in config_entry.data.items()
            if k not in (CONF_APPLIANCE_INFO, CONF_DESCRIPTION_FILENAME, CONF_FEATURE_FILENAME)
        }
        new_data[CONF_DESCRIPTION] = description
        await remove_description_files(hass, config_entry)
        _LOGGER.debug("Converted %s from v2 to v1 storage", description["info"].get("vib"))

    if new_data is not None or config_entry.version != 1:
        # VERSION is declared as 2 (see config_flow.py) purely so HA
        # doesn't hard-block an entry created by newer upstream code -
        # every entry this fork actually touches gets stamped back down to
        # 1 regardless, since 1 is the only version number any release of
        # this fork has ever understood. That keeps every entry we write
        # loadable by an older release of this fork too, not just newer
        # ones - rolling back doesn't hit the same hard block that a
        # genuinely higher, unrecognized version number would.
        hass.config_entries.async_update_entry(
            config_entry, data=new_data or config_entry.data, version=1
        )

    _LOGGER.debug("Setting up %s", config_entry.data[CONF_DESCRIPTION]["info"].get("model"))
    coordinator = HomeConnectCoordinator(hass, config_entry)
    appliance = coordinator.appliance
    if config_entry.unique_id is None:
        msg = "Config entry is missing its unique_id"
        raise ConfigEntryError(msg)
    device_info = DeviceInfo(
        hw_version=appliance.info.get("hwVersion"),
        identifiers={(DOMAIN, config_entry.unique_id)},
        model=f"{appliance.info.get('type')}",
        model_id=f"{appliance.info.get('vib')} / IP: {config_entry.data[CONF_HOST]}",
        serial_number=appliance.info.get("serialNumber"),
        sw_version=appliance.info.get("swVersion"),
    )

    if mac := appliance.info.get("mac"):
        device_info["connections"] = {(CONNECTION_NETWORK_MAC, format_mac(mac))}

    if brand := appliance.info.get("brand"):
        device_info["manufacturer"] = brand.capitalize()

    if (type_ := appliance.info.get("type")) and brand:
        device_info["name"] = f"{brand.capitalize()} {type_}"

    available_entities = get_available_entities(appliance)

    config_entry.runtime_data = HCData(
        appliance=appliance,
        device_info=device_info,
        available_entity_descriptions=available_entities,
        coordinator=coordinator,
    )

    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    async def _async_stop_listener(_event: Event) -> None:
        """Close the connection on Home Assistant shutdown."""
        await coordinator.close()

    config_entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_listener)
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HCConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading %s", entry.data[CONF_DESCRIPTION]["info"].get("vib"))
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.coordinator.close()
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, config_entry: HCConfigEntry) -> bool:  # noqa: ARG001
    """
    No-op: required by HA whenever VERSION > 1 is declared, never actually needed.

    VERSION = 2 exists purely so HA accepts an entry created by newer
    upstream chris-mc1/homeconnect_local_hass code instead of hard-blocking
    it (entry.version > declared VERSION refuses setup entirely, before
    calling any of our code). This only ever fires for entry.version < 2,
    i.e. a v1 entry - already CONF_DESCRIPTION-shaped, the only shape this
    fork wants, and async_setup_entry stamps every entry it touches back
    down to version 1 regardless (see there) rather than letting it drift
    to 2, so there's genuinely nothing to migrate here, ever.
    """
    return True
