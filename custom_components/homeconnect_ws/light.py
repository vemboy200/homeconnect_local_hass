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
    from collections.abc import Callable

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


def _brightness_value(entity: HcEntity, brightness: int) -> int:
    """Convert a Home Assistant brightness (0-255) to the appliance's 1-100 scale."""
    return int(
        max(brightness_to_value((1, 100), brightness), cast("float", getattr(entity, "min", 0.0)))
    )


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
        if (
            self._preset_active
            and self._brightness_entity is not None
            and self._brightness_entity.value is not None
        ):
            # A preset color has its own brightness Setting; the custom color's
            # hex value only describes the last custom color.
            return value_to_brightness((1, 100), cast("float", self._brightness_entity.value))
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

    @property
    def _preset_active(self) -> bool:
        """Whether a preset color (not CustomColor) is selected."""
        return self._color_mode_entity is not None and self._color_mode_entity.value not in (
            None,
            "CustomColor",
        )

    @property
    def _preset_brightness_usable(self) -> bool:
        """Whether the brightness Setting for a preset color can be written."""
        return (
            self._preset_active
            and self._brightness_entity is not None
            and entity_is_available(
                self._brightness_entity, self.entity_description.available_access
            )
        )

    @property
    def _custom_color_mode_pending(self) -> bool:
        """
        Whether the color mode can, and still needs to, be set to CustomColor.

        While a preset color is active, the LC91KWW60/04 hood offers the color
        mode Setting but not the custom color Setting at all; the custom color
        only becomes available once the mode is CustomColor (upstream #477).
        """
        if self._color_mode_entity is None:
            return False
        return (
            entity_is_available(self._color_mode_entity, self.entity_description.available_access)
            and self._color_mode_entity.value != "CustomColor"
        )

    async def _wait_until(self, condition: Callable[[], bool]) -> None:
        """
        Wait (bounded) until condition() holds after a write.

        The appliance reports Setting availability changes via a
        descriptionChange NOTIFY shortly after a write is acknowledged, so
        wait for that callback instead of firing blind. Times out silently;
        the caller re-checks availability before writing.
        """
        if condition():
            return
        entities = [
            entity
            for entity in (self._color_entity, self._color_mode_entity, self._brightness_entity)
            if entity is not None
        ]
        if not entities:
            return
        condition_met = asyncio.Event()

        async def _on_update(_: HcEntity) -> None:
            if condition():
                condition_met.set()

        for entity in entities:
            entity.register_callback(_on_update)
        try:
            async with asyncio.timeout(_RGB_AVAILABLE_TIMEOUT):
                await condition_met.wait()
        except TimeoutError:
            pass
        finally:
            for entity in entities:
                entity.unregister_callback(_on_update)

    async def _write(self, data: list[dict[str, Any]]) -> None:
        await self._runtime_data.appliance.session.send_sync(
            HC_Message(resource="/ro/values", action=Action.POST, data=data)
        )

    async def _turn_on_rgb(self, kwargs: dict[str, Any], *, powered_on_now: bool) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS, self.brightness)
        rgb = kwargs.get(ATTR_RGB_COLOR, self.rgb_color)
        if ATTR_RGB_COLOR not in kwargs and ATTR_BRIGHTNESS not in kwargs:
            # Plain turn-on: the appliance restores its last color itself,
            # so there is nothing to write and no reason to wait.
            return
        if powered_on_now:
            # The color Settings only become available after power-on.
            # Evaluating them before that would silently drop a color
            # passed with turn_on (e.g. picking a color while off).
            await self._wait_until(lambda: self._rgb_usable or self._custom_color_mode_pending)
        if ATTR_RGB_COLOR not in kwargs and self._preset_active:
            # Brightness-only change while a preset color is active: the
            # preset has its own brightness Setting. Switching to
            # CustomColor here would replace the preset with the last
            # custom color.
            await self._wait_until(lambda: self._preset_brightness_usable)
            if self._preset_brightness_usable and brightness is not None:
                brightness_entity = cast("HcEntity", self._brightness_entity)
                await self._write(
                    [
                        {
                            "uid": brightness_entity.uid,
                            "value": _brightness_value(brightness_entity, brightness),
                        }
                    ]
                )
            return
        if not self._rgb_usable and self._custom_color_mode_pending:
            # A preset color is active and the custom color Setting is not
            # offered: switch to CustomColor first, then wait for it.
            mode_entity = cast("HcEntity", self._color_mode_entity)
            color_mode_value = mode_entity._rev_enumeration["CustomColor"]  # noqa: SLF001
            await self._write([{"uid": mode_entity.uid, "value": color_mode_value}])
            await self._wait_until(lambda: self._rgb_usable)
        if not (self._rgb_usable and rgb is not None and brightness is not None):
            return
        color_entity = cast("HcEntity", self._color_entity)
        rgb_with_brightness = tuple(color * brightness // 255 for color in rgb)
        color_data: list[dict[str, Any]] = [
            {
                "uid": color_entity.uid,
                "value": "#" + color_rgb_to_hex(*rgb_with_brightness),
            }
        ]
        if self._color_mode_entity is not None and self._color_mode_entity.value != "CustomColor":
            color_mode_value = self._color_mode_entity._rev_enumeration["CustomColor"]  # noqa: SLF001
            color_data.append({"uid": self._color_mode_entity.uid, "value": color_mode_value})
        await self._write(color_data)

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

        if self._attr_color_mode == ColorMode.RGB:
            await self._turn_on_rgb(kwargs, powered_on_now=powered_on_now)
            return

        brightness = kwargs.get(ATTR_BRIGHTNESS, self.brightness)
        message_data: list[dict[str, Any]] = []
        if (
            self._attr_color_mode in (ColorMode.BRIGHTNESS, ColorMode.COLOR_TEMP)
            and ATTR_BRIGHTNESS in kwargs
            and brightness is not None
        ):
            brightness_entity = cast("HcEntity", self._brightness_entity)
            message_data.append(
                {
                    "uid": brightness_entity.uid,
                    "value": _brightness_value(brightness_entity, brightness),
                }
            )

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
