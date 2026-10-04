"""Light entities."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from home_disconnect.message import Action
from home_disconnect.message import Message as HC_Message
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    LightEntity,
)
from homeassistant.components.light.const import (
    DEFAULT_MAX_KELVIN,
    DEFAULT_MIN_KELVIN,
    ColorMode,
)
from homeassistant.util.color import (
    brightness_to_value,
    color_rgb_to_hex,
    match_max_scale,
    rgb_hex_to_rgb_list,
    value_to_brightness,
)
from homeassistant.util.scaling import scale_ranged_value_to_int_range

from .entity import HCEntity
from .helpers import create_entities, entity_is_available, error_decorator

if TYPE_CHECKING:
    from home_disconnect.entities import Entity as HcEntity
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import HCConfigEntry, HCData
    from .entity_descriptions.descriptions_definitions import HCLightEntityDescription

PARALLEL_UPDATES = 0

# After a power-on write, ambient lights report their color Settings as
# available via a descriptionChange NOTIFY (~60 ms on a Siemens LC91KWW60/04,
# upstream #477). Wait for it, but give up quickly if it never arrives.
_RGB_AVAILABLE_TIMEOUT = 2.0


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    config_entry: HCConfigEntry,
    async_add_entites: AddEntitiesCallback,
) -> None:
    """Set up light platform."""
    entities = create_entities({"light": HCLight}, config_entry.runtime_data)
    async_add_entites(entities)


class HCLight(HCEntity, LightEntity):
    """Light Entity."""

    entity_description: HCLightEntityDescription
    _brightness_entity: HcEntity | None = None
    _color_temperature_entity: HcEntity | None = None
    _color_entity: HcEntity | None = None
    _color_mode_entity: HcEntity | None = None
    _color_temp_presets_entity: HcEntity | None = None

    def __init__(
        self,
        entity_description: HCLightEntityDescription,
        runtime_data: HCData,
    ) -> None:
        super().__init__(entity_description, runtime_data)
        if entity_description.brightness_entity is not None:
            self._brightness_entity = self._runtime_data.appliance.entities[
                entity_description.brightness_entity
            ]
            self._entities.append(self._brightness_entity)

        if entity_description.color_temperature_entity is not None:
            self._color_temperature_entity = self._runtime_data.appliance.entities[
                entity_description.color_temperature_entity
            ]
            self._entities.append(self._color_temperature_entity)
            self._color_temp_presets_entity = self._runtime_data.appliance.entities.get(
                "Cooking.Hood.Setting.ColorTemperature"
            )

        if entity_description.color_entity is not None:
            self._color_entity = self._runtime_data.appliance.entities[
                entity_description.color_entity
            ]
            self._entities.append(self._color_entity)

        if entity_description.color_mode_entity is not None:
            self._color_mode_entity = self._runtime_data.appliance.entities[
                entity_description.color_mode_entity
            ]
            self._entities.append(self._color_mode_entity)

        if self._color_entity:
            self._attr_supported_color_modes = {ColorMode.RGB}
            self._attr_color_mode = ColorMode.RGB
        elif self._color_temperature_entity and self._brightness_entity:
            self._attr_supported_color_modes = {ColorMode.COLOR_TEMP}
            self._attr_color_mode = ColorMode.COLOR_TEMP
            self._attr_max_color_temp_kelvin = DEFAULT_MAX_KELVIN
            self._attr_min_color_temp_kelvin = DEFAULT_MIN_KELVIN
        elif self._brightness_entity:
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_supported_color_modes = {ColorMode.ONOFF}
            self._attr_color_mode = ColorMode.ONOFF

    @property
    def is_on(self) -> bool | None:
        if self._entity is None:
            return None
        if self._entity.value is None:
            # Not reported by the appliance yet - "unknown", not "off".
            return None
        return bool(self._entity.value)

    @property
    def brightness(self) -> int | None:
        # Brightness/color-temp/color entities can be unavailable while still
        # declared (e.g. only reported while the light is on) - confirmed
        # live on fork issue #15 (Bosch DWK91LT60). A missing value here is
        # normal, not an error: fall back to None rather than crashing on a
        # None-valued conversion, and don't gate the whole entity's
        # availability on these secondary capabilities (see is_on/available).
        if self._color_entity is not None and self._color_entity.value is not None:
            rgb = rgb_hex_to_rgb_list(cast("str", self._color_entity.value).strip("#"))
            return max(rgb)
        if self._brightness_entity is not None and self._brightness_entity.value is not None:
            return value_to_brightness((1, 100), cast("float", self._brightness_entity.value))
        return None

    @property
    def color_temp_kelvin(self) -> int | None:
        if (
            self._color_temperature_entity is not None
            and self._color_temperature_entity.value is not None
        ):
            color_temp_value = cast("float", self._color_temperature_entity.value)
            if self._color_temp_presets_entity:
                return scale_ranged_value_to_int_range(
                    (101, 0),
                    (DEFAULT_MIN_KELVIN + 1, DEFAULT_MAX_KELVIN),
                    color_temp_value,
                )

            return scale_ranged_value_to_int_range(
                (1, 100),
                (DEFAULT_MIN_KELVIN + 1, DEFAULT_MAX_KELVIN),
                color_temp_value,
            )
        return None

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        if self._color_entity is not None and self._color_entity.value is not None:
            rgb = rgb_hex_to_rgb_list(cast("str", self._color_entity.value).strip("#"))
            return cast("tuple[int, int, int]", match_max_scale((255,), tuple(rgb)))
        return None

    @property
    def _rgb_usable(self) -> bool:
        """
        Whether the appliance currently offers the color Setting.

        Ambient lights report their color Setting as unavailable while the
        light is off, so writing a color then would hit a Setting the
        appliance rejects with WriteRequest NotAvailable (upstream #477).
        """
        if self._color_entity is None:
            return False
        return entity_is_available(self._color_entity, self.entity_description.available_access)

    async def _wait_for_rgb_usable(self) -> None:
        """
        Wait for the color Setting to become available after power-on.

        The appliance flips the color Settings to available with a
        descriptionChange NOTIFY shortly after the power-on write is
        acknowledged. Writing the color before that is rejected with
        WriteRequest NotAvailable, so wait for the callback instead of
        firing blind. Times out silently; _rgb_usable then skips the color.
        """
        if self._color_entity is None or self._rgb_usable:
            return
        became_usable = asyncio.Event()

        async def _on_update(_: HcEntity) -> None:
            if self._rgb_usable:
                became_usable.set()

        self._color_entity.register_callback(_on_update)
        try:
            async with asyncio.timeout(_RGB_AVAILABLE_TIMEOUT):
                await became_usable.wait()
        except TimeoutError:
            pass
        finally:
            self._color_entity.unregister_callback(_on_update)

    async def _write(self, data: list[dict[str, Any]]) -> None:
        await self._runtime_data.appliance.session.send_sync(
            HC_Message(resource="/ro/values", action=Action.POST, data=data)
        )

    @error_decorator
    async def async_turn_on(self, **kwargs: Any) -> None:
        powered_on_now = False
        if self._entity is not None and self._entity.value is not True:
            # Sent as its own write, before any color/brightness/color-temp
            # data, rather than bundled into one combined message - some
            # appliances reject the combined form outright (confirmed live on
            # upstream #477, a Siemens LC91KWW60/04 ambient light: a bare
            # power-on write succeeds, one that also carries a color value
            # gets the whole message rejected with WriteRequest NotAvailable).
            await self._write([{"uid": self._entity.uid, "value": True}])
            powered_on_now = True

        brightness = kwargs.get(ATTR_BRIGHTNESS, self.brightness)
        rgb = kwargs.get(ATTR_RGB_COLOR, self.rgb_color)

        if self._attr_color_mode == ColorMode.RGB:
            if powered_on_now:
                # The color Settings only become available after power-on.
                # Evaluating _rgb_usable before that would silently drop a
                # color passed with turn_on (e.g. picking a color while off).
                await self._wait_for_rgb_usable()
            if not (self._rgb_usable and rgb is not None and brightness is not None):
                return
            # Color mode goes first, as its own write: the custom color
            # Setting may only accept a value once the mode is CustomColor.
            if (
                self._color_mode_entity is not None
                and self._color_mode_entity.value != "CustomColor"
            ):
                color_mode_value = self._color_mode_entity._rev_enumeration["CustomColor"]  # noqa: SLF001
                await self._write([{"uid": self._color_mode_entity.uid, "value": color_mode_value}])
            color_entity = cast("HcEntity", self._color_entity)
            rgb_with_brightness = tuple(color * brightness // 255 for color in rgb)
            await self._write(
                [
                    {
                        "uid": color_entity.uid,
                        "value": "#" + color_rgb_to_hex(*rgb_with_brightness),
                    }
                ]
            )
            return

        message_data: list[dict[str, Any]] = []
        if (
            self._attr_color_mode in (ColorMode.BRIGHTNESS, ColorMode.COLOR_TEMP)
            and ATTR_BRIGHTNESS in kwargs
            and brightness is not None
        ):
            brightness_entity = cast("HcEntity", self._brightness_entity)
            value_in_range = int(
                max(
                    brightness_to_value((1, 100), brightness),
                    cast("float", getattr(brightness_entity, "min", 0.0)),
                )
            )
            message_data.append({"uid": brightness_entity.uid, "value": value_in_range})

        if ATTR_COLOR_TEMP_KELVIN in kwargs and self._color_temperature_entity is not None:
            if self._color_temp_presets_entity:
                value_in_range = int(
                    scale_ranged_value_to_int_range(
                        (DEFAULT_MIN_KELVIN + 1, DEFAULT_MAX_KELVIN),
                        (101, 0),
                        kwargs[ATTR_COLOR_TEMP_KELVIN],
                    )
                )
                message_data.append({"uid": self._color_temp_presets_entity.uid, "value": 0})
            else:
                value_in_range = int(
                    scale_ranged_value_to_int_range(
                        (DEFAULT_MIN_KELVIN + 1, DEFAULT_MAX_KELVIN),
                        (1, 100),
                        kwargs[ATTR_COLOR_TEMP_KELVIN],
                    )
                )
            message_data.append(
                {"uid": self._color_temperature_entity.uid, "value": value_in_range}
            )

        if message_data:
            await self._write(message_data)

    @error_decorator
    async def async_turn_off(self, **kwargs: Any) -> None:
        if self._entity is not None:
            await self._entity.set_value(False)
