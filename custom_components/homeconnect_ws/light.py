"""Light entities."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from home_disconnect import AccessError
from homeassistant.components.light import LightEntity
from homeassistant.components.light.const import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    DEFAULT_MAX_KELVIN,
    DEFAULT_MIN_KELVIN,
    ColorMode,
)
from homeassistant.util.color import (
    brightness_to_value,
    match_max_scale,
    rgb_hex_to_rgb_list,
    value_to_brightness,
)
from homeassistant.util.scaling import scale_ranged_value_to_int_range

from .entity import HCEntity
from .helpers import create_entities, error_decorator

if TYPE_CHECKING:
    from home_disconnect.entities import Entity as HcEntity
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import HCConfigEntry, HCData
    from .entity_descriptions.descriptions_definitions import HCLightEntityDescription

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


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
    def _preset_active(self) -> bool:
        """Whether a preset color (not CustomColor) is selected."""
        return self._color_mode_entity is not None and self._color_mode_entity.value not in (
            None,
            "CustomColor",
        )

    async def _write(self, data: list[dict[str, Any]]) -> None:
        await self._runtime_data.appliance.set_values_raw(
            {item["uid"]: item["value"] for item in data}
        )

    async def _turn_on_ambient(self, kwargs: dict[str, Any]) -> None:
        """Turn on an ambient light; the library waits for its color Settings (upstream #477)."""
        brightness = kwargs.get(ATTR_BRIGHTNESS, self.brightness)
        rgb = kwargs.get(ATTR_RGB_COLOR, self.rgb_color)
        change: dict[str, Any] = {}
        if ATTR_RGB_COLOR not in kwargs and ATTR_BRIGHTNESS in kwargs and self._preset_active:
            # A preset color has its own brightness Setting. Switching to CustomColor here would
            # replace the preset with the last custom color.
            brightness_entity = cast("HcEntity", self._brightness_entity)
            change["brightness"] = _brightness_value(brightness_entity, kwargs[ATTR_BRIGHTNESS])
        elif (ATTR_RGB_COLOR in kwargs or ATTR_BRIGHTNESS in kwargs) and (
            rgb is not None and brightness is not None
        ):
            # The custom color carries the brightness: (128, 0, 0) is a dimmer red.
            change["color"] = tuple(c * brightness // 255 for c in rgb)
        # With neither, it's a plain turn-on: the appliance restores its last color itself.
        try:
            await self._runtime_data.appliance.set_ambient_light(**change)
        except AccessError:
            # The color Settings never became available after power-on (upstream #477): the
            # light is on, just without the change.
            _LOGGER.debug("%s: color or brightness not available, not set", self.entity_id)

    @error_decorator
    async def async_turn_on(self, **kwargs: Any) -> None:
        if self._attr_color_mode == ColorMode.RGB:
            await self._turn_on_ambient(kwargs)
            return

        if self._entity is not None and self._entity.value is not True:
            # Sent as its own write, before any brightness/color-temp data, rather than bundled
            # into one message - some appliances reject the combined form outright (upstream
            # #477, a Siemens LC91KWW60/04).
            await self._write([{"uid": self._entity.uid, "value": True}])

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
