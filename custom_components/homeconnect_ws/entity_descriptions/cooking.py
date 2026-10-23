"""Description for Cooking Entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from home_disconnect.entities import Access
from home_disconnect.keys import CommandKey, EventKey, OptionKey, ProgramKey, SettingKey, StatusKey
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.components.number import NumberDeviceClass, NumberMode
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.switch.const import SwitchDeviceClass
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfMass,
    UnitOfTemperature,
    UnitOfTime,
)

from .descriptions_definitions import (
    HCBinarySensorEntityDescription,
    HCButtonEntityDescription,
    HCFanEntityDescription,
    HCLightEntityDescription,
    HCNumberEntityDescription,
    HCSelectEntityDescription,
    HCSensorEntityDescription,
    HCSwitchEntityDescription,
    _EntityDescriptionsDefinitionsType,
    keep_known_events,
)

if TYPE_CHECKING:
    from home_disconnect import Appliance

_VENTING_PROGRAM = ProgramKey.COOKING_COMMON_HOOD_VENTING


def _temperature_entity(
    appliance: Appliance,
    base: str,
) -> tuple[str, UnitOfTemperature] | None:
    """Return the first temperature entity present on the appliance."""
    for suffix, unit in (
        ("CurrentTemperature", UnitOfTemperature.CELSIUS),
        ("CurrentTemperatureFahrenheit", UnitOfTemperature.FAHRENHEIT),
    ):
        entity = f"{base}{suffix}"
        if entity in appliance.entities:
            return entity, unit
    return None


def _meatprobe_entity(
    appliance: Appliance,
    cavity: str,
) -> tuple[str, UnitOfTemperature] | None:
    """Return the first meat-probe temperature entity present on the appliance."""
    base = f"Cooking.Oven.Status.Cavity.{cavity}."
    for suffix, unit in (
        ("CurrentMeatprobeTemperature", UnitOfTemperature.CELSIUS),
        ("CurrentMeatprobeTemperatureFahrenheit", UnitOfTemperature.FAHRENHEIT),
        ("MeatProbeTemperatureFahrenheit", UnitOfTemperature.FAHRENHEIT),
    ):
        entity = f"{base}{suffix}"
        if entity in appliance.entities:
            return entity, unit
    return None


# The fields a cavity reports only so the Home Connect app can draw the
# appliance front - nothing to show or control on their own.
_CAVITY_LAYOUT_FIELDS = frozenset({"CavityType", "State", "LengthX", "LengthY", "Position"})


def _is_layout_only_cavity(appliance: Appliance, cavity: str) -> bool:
    """
    Whether a cavity reports nothing but its layout fields.

    A Thermador PRG486WDH range's non-smart 18" oven (cavity 120) is one: it
    reports State NotSelectable plus the layout fields, while the smart 30"
    oven (cavity 340) carries everything else.
    """
    prefix = f"Cooking.Oven.Status.Cavity.{cavity}."
    return all(
        name.removeprefix(prefix) in _CAVITY_LAYOUT_FIELDS
        for name in appliance.entities
        if name.startswith(prefix)
    )


def _oven_status_cavities(appliance: Appliance) -> dict[str, str]:
    """
    Return each status cavity with its name suffix.

    Only cavities with something to show need telling apart - a layout-only
    cavity creates no entities, so it mustn't add a "340" suffix to the
    names of the one real cavity.
    """
    groups = appliance.group_ids(StatusKey.COOKING_OVEN_CAVITY)
    real_cavities = [group for group in groups if not _is_layout_only_cavity(appliance, group)]
    return {group: "" if len(real_cavities) <= 1 else f" {int(group)}" for group in groups}


def generate_oven_water_tank(appliance: Appliance) -> list[HCSensorEntityDescription]:
    """Get the per-cavity Water tank descriptions."""
    descriptions = []
    for group, group_name in _oven_status_cavities(appliance).items():
        entities = [
            f"Cooking.Oven.Status.Cavity.{group}.WaterTankUnplugged",
            f"Cooking.Oven.Status.Cavity.{group}.WaterTankEmpty",
        ]
        water_tank = keep_known_events(
            HCSensorEntityDescription(
                key=f"sensor_oven_water_tank_{group}",
                translation_key="sensor_oven_water_tank_group",
                translation_placeholders={"group_name": group_name},
                entities=entities,
                device_class=SensorDeviceClass.ENUM,
                options=["unplugged", "empty", "ok"],
            ),
            appliance.entities,
        )
        if water_tank is not None:
            descriptions.append(water_tank)
    return descriptions


def generate_oven_temperatures(appliance: Appliance) -> list[HCSensorEntityDescription]:
    """Get the per-cavity Current temperature and Meat probe temperature descriptions."""
    descriptions = []
    for group, group_name in _oven_status_cavities(appliance).items():
        # Temperature (Celsius or Fahrenheit depending on appliance locale)
        cavity_base = f"Cooking.Oven.Status.Cavity.{group}."
        if temperature := _temperature_entity(appliance, cavity_base):
            entity, unit = temperature
            descriptions.append(
                HCSensorEntityDescription(
                    key=f"sensor_oven_current_temperature_{group}",
                    translation_key="sensor_oven_current_temperature_group",
                    translation_placeholders={"group_name": group_name},
                    entity=entity,
                    device_class=SensorDeviceClass.TEMPERATURE,
                    native_unit_of_measurement=unit,
                )
            )

        if meatprobe := _meatprobe_entity(appliance, group):
            entity, unit = meatprobe
            descriptions.append(
                HCSensorEntityDescription(
                    key=f"sensor_oven_current_meatprobe_temperature_{group}",
                    translation_key="sensor_oven_current_meatprobe_temperature",
                    translation_placeholders={"group_name": group_name},
                    entity=entity,
                    device_class=SensorDeviceClass.TEMPERATURE,
                    native_unit_of_measurement=unit,
                )
            )
    return descriptions


def generate_cavity_meatprobe_plugged(
    appliance: Appliance,
) -> list[HCBinarySensorEntityDescription]:
    """Get the per-cavity Meat probe plugged descriptions."""
    descriptions = []
    for group, group_name in _oven_status_cavities(appliance).items():
        entity = f"Cooking.Oven.Status.Cavity.{group}.MeatprobePlugged"
        if entity in appliance.entities:
            descriptions.append(
                HCBinarySensorEntityDescription(
                    key=f"binary_sensor_oven_meatprobe_plugged_{group}",
                    translation_key="binary_sensor_oven_meatprobe_plugged",
                    translation_placeholders={"group_name": group_name},
                    entity=entity,
                    device_class=BinarySensorDeviceClass.PLUG,
                    entity_category=EntityCategory.DIAGNOSTIC,
                )
            )
    return descriptions


# What the oven asks for or reports while cooking: event name, key, device class
_OVEN_COOKING_EVENTS = (
    ("InsertFoodNow", "binary_sensor_oven_insert_food_now", None),
    ("TurnFoodNow", "binary_sensor_oven_turn_food_now", None),
    ("RegularPreheatFinished", "binary_sensor_oven_regular_preheat_finished", None),
    ("FastPreheatFinished", "binary_sensor_oven_fast_preheat_finished", None),
    ("ProgramFinished", "binary_sensor_oven_program_finished", None),
    ("ProgramAborted", "binary_sensor_oven_program_aborted", None),
    ("OpenDoor", "binary_sensor_oven_open_door", None),
    ("CloseDoor", "binary_sensor_oven_close_door", None),
    (
        "CavityTemperatureTooHigh",
        "binary_sensor_oven_cavity_temperature_too_high",
        BinarySensorDeviceClass.PROBLEM,
    ),
)


def generate_oven_event(appliance: Appliance) -> list[HCBinarySensorEntityDescription]:
    """Get Oven event descriptions."""
    groups = appliance.group_ids(EventKey.COOKING_OVEN_CAVITY)
    descriptions: list[HCBinarySensorEntityDescription] = []
    for group in groups:
        group_name = f" {int(group)}"
        if len(groups) == 1:
            group_name = ""

        # AlarmClockElapsed
        entity = f"Cooking.Oven.Event.Cavity.{group}.AlarmClockElapsed"
        if entity in appliance.entities:
            descriptions.append(
                HCBinarySensorEntityDescription(
                    key=f"binary_sensor_oven_alarm_clock_elapsed_{group}",
                    translation_key="binary_sensor_oven_alarm_clock_elapsed",
                    translation_placeholders={"group_name": group_name},
                    entity=entity,
                    value_on={"Present", "Confirmed"},
                    value_off={"Off"},
                )
            )

        for event, key, device_class in _OVEN_COOKING_EVENTS:
            entity = f"Cooking.Oven.Event.Cavity.{group}.{event}"
            if entity in appliance.entities:
                descriptions.append(
                    HCBinarySensorEntityDescription(
                        key=f"{key}_{group}",
                        translation_key=key,
                        translation_placeholders={"group_name": group_name},
                        entity=entity,
                        device_class=device_class,
                        # Problem sensors feed the appliance's Problem sensor instead
                        entity_registry_enabled_default=device_class is None,
                        value_on={"Present", "Confirmed"},
                        value_off={"Off"},
                    )
                )

    return descriptions


def generate_oven_settings(appliance: Appliance) -> list[HCNumberEntityDescription]:
    """Get the per-cavity Alarm clock descriptions."""
    groups = appliance.group_ids(SettingKey.COOKING_OVEN_CAVITY)
    descriptions: list[HCNumberEntityDescription] = []
    for group in groups:
        group_name = f" {int(group)}"
        if len(groups) == 1:
            group_name = ""

        # AlarmClock
        entity = f"Cooking.Oven.Setting.Cavity.{group}.AlarmClock"
        if entity in appliance.entities:
            descriptions.append(
                HCNumberEntityDescription(
                    key=f"number_oven_setting_{group}_alarm_clock",
                    translation_key="number_setting_alarm_clock_groupe",
                    translation_placeholders={"group_name": group_name},
                    entity=entity,
                    device_class=NumberDeviceClass.DURATION,
                    native_unit_of_measurement=UnitOfTime.SECONDS,
                    native_max_value=86400,  # 24 hours, matching the Home Connect App's limit
                    mode=NumberMode.BOX,
                )
            )

    return descriptions


def generate_meatprobe_plugged(appliance: Appliance) -> HCBinarySensorEntityDescription | None:
    """
    Get the appliance-wide Meat probe plugged description.

    Left out when the oven also reports it per cavity (generate_cavity_meatprobe_plugged
    adds those), which some ovens (e.g. the Thermador PRG486WDH) do for the
    same probe.
    """
    if StatusKey.COOKING_OVEN_MEATPROBE_PLUGGED not in appliance.entities or any(
        f"Cooking.Oven.Status.Cavity.{group}.MeatprobePlugged" in appliance.entities
        for group in appliance.group_ids(StatusKey.COOKING_OVEN_CAVITY)
    ):
        return None
    return HCBinarySensorEntityDescription(
        key="binary_sensor_oven_meatprobe_plugged",
        entity=StatusKey.COOKING_OVEN_MEATPROBE_PLUGGED,
        device_class=BinarySensorDeviceClass.PLUG,
        entity_category=EntityCategory.DIAGNOSTIC,
    )


HOOD_FAN_ENTITIES = [
    OptionKey.COOKING_COMMON_HOOD_VENTING_LEVEL,
    OptionKey.COOKING_COMMON_HOOD_INTENSIVE_LEVEL,
]


def generate_hood_fan(appliance: Appliance) -> HCFanEntityDescription | None:
    """Get Hood Fan description."""
    if _VENTING_PROGRAM not in appliance.programs:
        return None

    venting = appliance.programs[_VENTING_PROGRAM]
    available_entities = [
        option.name
        for option in venting.options
        if option.name in HOOD_FAN_ENTITIES and option.access == Access.READ_WRITE
    ]
    if not available_entities:
        return None

    return HCFanEntityDescription(
        key="fan_hood",
        entities=available_entities,
    )


def generate_hob_zones(appliance: Appliance) -> list[HCSensorEntityDescription]:
    """Get the per-zone Hob descriptions."""
    groups = appliance.group_ids(StatusKey.COOKING_HOB_ZONE)
    descriptions: list[HCSensorEntityDescription] = []
    for group in groups:
        group_name = f" {int(group)}"
        if len(groups) == 1:
            group_name = ""

        # State
        entity = f"Cooking.Hob.Status.Zone.{group}.State"
        if entity in appliance.entities:
            descriptions.append(
                HCSensorEntityDescription(
                    key=f"sensor_hob_zone_{group}_state",
                    translation_key="sensor_hob_zone_state",
                    translation_placeholders={"group_name": group_name},
                    entity=entity,
                    device_class=SensorDeviceClass.ENUM,
                    has_state_translation=True,
                    extra_attributes=[
                        {
                            "name": "Type",
                            "entity": f"Cooking.Hob.Status.Zone.{group}.Type",
                        }
                    ],
                )
            )

        # OperationState
        entity = f"Cooking.Hob.Status.Zone.{group}.OperationState"
        if entity in appliance.entities:
            descriptions.append(
                HCSensorEntityDescription(
                    key=f"sensor_hob_zone_{group}_operationstate",
                    translation_key="sensor_hob_zone_operationstate",
                    translation_placeholders={"group_name": group_name},
                    entity=entity,
                    device_class=SensorDeviceClass.ENUM,
                    has_state_translation=True,
                )
            )

        # PowerLevel
        entity = f"Cooking.Hob.Status.Zone.{group}.PowerLevel"
        if entity in appliance.entities:
            descriptions.append(
                HCSensorEntityDescription(
                    key=f"sensor_hob_zone_{group}_power_level",
                    translation_key="sensor_hob_zone_power_level",
                    translation_placeholders={"group_name": group_name},
                    entity=entity,
                    device_class=SensorDeviceClass.ENUM,
                    has_state_translation=True,
                )
            )

        # FryingSensorLevel
        entity = f"Cooking.Hob.Status.Zone.{group}.FryingSensorLevel"
        if entity in appliance.entities:
            descriptions.append(
                HCSensorEntityDescription(
                    key=f"sensor_hob_zone_{group}_frying_sensor_level",
                    translation_key="sensor_hob_zone_frying_sensor_level",
                    translation_placeholders={"group_name": group_name},
                    entity=entity,
                    device_class=SensorDeviceClass.ENUM,
                    has_state_translation=True,
                )
            )

        # CurrentTemperature
        entity = f"Cooking.Hob.Status.Zone.{group}.CurrentTemperature"
        if entity in appliance.entities:
            descriptions.append(
                HCSensorEntityDescription(
                    key=f"sensor_hob_zone_{group}_current_temperature",
                    translation_key="sensor_hob_zone_current_temperature",
                    translation_placeholders={"group_name": group_name},
                    entity=entity,
                    device_class=SensorDeviceClass.TEMPERATURE,
                    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                )
            )

        # HeatupProgress
        entity = f"Cooking.Hob.Status.Zone.{group}.HeatupProgress"
        if entity in appliance.entities:
            descriptions.append(
                HCSensorEntityDescription(
                    key=f"sensor_hob_zone_{group}_heatup_progress",
                    translation_key="sensor_hob_zone_heatup_progress",
                    translation_placeholders={"group_name": group_name},
                    entity=entity,
                    native_unit_of_measurement=PERCENTAGE,
                )
            )

        # Duration
        entity = f"Cooking.Hob.Status.Zone.{group}.Duration"
        if entity in appliance.entities:
            descriptions.append(
                HCSensorEntityDescription(
                    key=f"sensor_hob_zone_{group}_duration",
                    translation_key="sensor_hob_zone_duration",
                    translation_placeholders={"group_name": group_name},
                    entity=entity,
                    device_class=SensorDeviceClass.DURATION,
                    native_unit_of_measurement=UnitOfTime.SECONDS,
                    suggested_unit_of_measurement=UnitOfTime.MINUTES,
                )
            )

        # ElapsedProgramTime
        entity = f"Cooking.Hob.Status.Zone.{group}.ElapsedProgramTime"
        extra_entity = f"Cooking.Hob.Status.Zone.{group}.ElapsedProgramTime.AutoCounting"
        if entity in appliance.entities:
            descriptions.append(
                HCSensorEntityDescription(
                    key=f"sensor_hob_zone_{group}_elapsed_program_time",
                    translation_key="sensor_hob_zone_elapsed_program_time",
                    translation_placeholders={"group_name": group_name},
                    entity=entity,
                    device_class=SensorDeviceClass.DURATION,
                    native_unit_of_measurement=UnitOfTime.SECONDS,
                    suggested_unit_of_measurement=UnitOfTime.MINUTES,
                    extra_attributes=[{"name": "Auto Counting", "entity": extra_entity}],
                )
            )

        # RemainingProgramTime
        entity = f"Cooking.Hob.Status.Zone.{group}.RemainingProgramTime"
        extra_entity = f"Cooking.Hob.Status.Zone.{group}.RemainingProgramTime.AutoCounting"
        if entity in appliance.entities:
            descriptions.append(
                HCSensorEntityDescription(
                    key=f"sensor_hob_zone_{group}_remaining_program_time",
                    translation_key="sensor_hob_zone_remaining_program_time",
                    translation_placeholders={"group_name": group_name},
                    entity=entity,
                    device_class=SensorDeviceClass.DURATION,
                    native_unit_of_measurement=UnitOfTime.SECONDS,
                    suggested_unit_of_measurement=UnitOfTime.MINUTES,
                    extra_attributes=[{"name": "Auto Counting", "entity": extra_entity}],
                )
            )

        # ProgramProgress
        entity = f"Cooking.Hob.Status.Zone.{group}.ProgramProgress"
        if entity in appliance.entities:
            descriptions.append(
                HCSensorEntityDescription(
                    key=f"sensor_hob_zone_{group}_program_progress",
                    translation_key="sensor_hob_zone_program_progress",
                    translation_placeholders={"group_name": group_name},
                    entity=entity,
                    native_unit_of_measurement=PERCENTAGE,
                )
            )

    return descriptions


def generate_hood_light(appliance: Appliance) -> HCLightEntityDescription | None:
    """Get Hood light description."""

    # Some hoods declare ColorTemperaturePercent/LightingBrightness in their
    # profile but mark them unavailable (confirmed live on fork issue #15,
    # Bosch DWK91LT60) - checking membership alone picked the wrong branch
    # and referenced an unavailable entity, making the whole light entity
    # report Unavailable even though the plain on/off Lighting control works
    # fine on its own.
    def available(name: str) -> bool:
        return bool(getattr(appliance.entities.get(name), "available", False))

    color_temperature = available(SettingKey.COOKING_HOOD_COLOR_TEMPERATURE_PERCENT)
    brightness = (
        color_temperature
        or available(SettingKey.COOKING_HOOD_LIGHTING_BRIGHTNESS)
        or available(SettingKey.COOKING_COMMON_LIGHTING_BRIGHTNESS)
    )
    if not brightness and not available(SettingKey.COOKING_COMMON_LIGHTING):
        return None
    return HCLightEntityDescription(
        key="light_cooking_lighting",
        entity=SettingKey.COOKING_COMMON_LIGHTING,
        brightness_entity=SettingKey.COOKING_COMMON_LIGHTING_BRIGHTNESS if brightness else None,
        color_temperature_entity=(
            SettingKey.COOKING_HOOD_COLOR_TEMPERATURE_PERCENT if color_temperature else None
        ),
    )


def generate_hood_ambient_light(appliance: Appliance) -> HCLightEntityDescription | None:
    """Get Hood ambient light description."""
    color = (
        SettingKey.BSH_COMMON_AMBIENT_LIGHT_CUSTOM_COLOR in appliance.entities
        and SettingKey.BSH_COMMON_AMBIENT_LIGHT_COLOR in appliance.entities
    )
    brightness = color or SettingKey.BSH_COMMON_AMBIENT_LIGHT_BRIGHTNESS in appliance.entities
    if not brightness and SettingKey.BSH_COMMON_AMBIENT_LIGHT_ENABLED not in appliance.entities:
        return None
    return HCLightEntityDescription(
        key="light_cooking_ambient_lighting",
        entity=SettingKey.BSH_COMMON_AMBIENT_LIGHT_ENABLED,
        brightness_entity=SettingKey.BSH_COMMON_AMBIENT_LIGHT_BRIGHTNESS if brightness else None,
        color_entity=SettingKey.BSH_COMMON_AMBIENT_LIGHT_CUSTOM_COLOR if color else None,
        color_mode_entity=SettingKey.BSH_COMMON_AMBIENT_LIGHT_COLOR if color else None,
    )


def generate_oven_cavity_light(appliance: Appliance) -> HCLightEntityDescription | None:
    """Get oven cavity light description."""
    if SettingKey.COOKING_OVEN_LIGHT_CAVITY_001_POWER not in appliance.entities:
        return None
    brightness = SettingKey.COOKING_OVEN_LIGHT_CAVITY_001_BRIGHTNESS
    return HCLightEntityDescription(
        key="light_oven_cavity",
        entity=SettingKey.COOKING_OVEN_LIGHT_CAVITY_001_POWER,
        brightness_entity=brightness if brightness in appliance.entities else None,
    )


COOKING_ENTITY_DESCRIPTIONS: _EntityDescriptionsDefinitionsType = {
    "sensor": [
        generate_oven_temperatures,
        generate_hob_zones,
        HCSensorEntityDescription(
            key="sensor_heatup_progress",
            entity=OptionKey.COOKING_OVEN_HEATUP_PROGRESS,
            native_unit_of_measurement=PERCENTAGE,
        ),
        HCSensorEntityDescription(
            key="sensor_grease_filter_saturation",
            entity=StatusKey.COOKING_HOOD_GREASE_FILTER_SATURATION,
            native_unit_of_measurement=PERCENTAGE,
        ),
        HCSensorEntityDescription(
            key="sensor_carbon_filter_saturation",
            entity=StatusKey.COOKING_HOOD_CARBON_FILTER_SATURATION,
            native_unit_of_measurement=PERCENTAGE,
        ),
        HCSensorEntityDescription(
            key="sensor_oven_water_tank",
            entities=[
                StatusKey.COOKING_OVEN_WATER_TANK_UNPLUGGED,
                StatusKey.COOKING_OVEN_WATER_TANK_EMPTY,
            ],
            device_class=SensorDeviceClass.ENUM,
            options=["unplugged", "empty", "ok"],
        ),
        HCSensorEntityDescription(
            key="sensor_oven_current_temperature",
            entity=StatusKey.COOKING_OVEN_CURRENT_CAVITY_TEMPERATURE,
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        HCSensorEntityDescription(
            key="sensor_oven_current_meatprobe_temperature",
            entity=StatusKey.COOKING_OVEN_CURRENT_MEATPROBE_TEMPERATURE,
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        HCSensorEntityDescription(
            key="sensor_oven_current_meatprobe_temperature_fahrenheit",
            translation_key="sensor_oven_current_meatprobe_temperature",
            entity=StatusKey.COOKING_OVEN_CURRENT_MEATPROBE_TEMPERATURE_FAHRENHEIT,
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        ),
    ],
    "event_sensor": [generate_oven_water_tank],
    "number": [
        generate_oven_settings,
        HCNumberEntityDescription(
            key="number_oven_setpoint_temperature",
            entity=OptionKey.COOKING_OVEN_SETPOINT_TEMPERATURE,
            device_class=NumberDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            mode=NumberMode.AUTO,
        ),
        HCNumberEntityDescription(
            key="number_oven_setpoint_temperature_fahrenheit",
            translation_key="number_oven_setpoint_temperature",
            entity=OptionKey.COOKING_OVEN_SETPOINT_TEMPERATURE_FAHRENHEIT,
            device_class=NumberDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
            mode=NumberMode.AUTO,
        ),
        HCNumberEntityDescription(
            key="number_oven_weight",
            entity=OptionKey.COOKING_OVEN_WEIGHT,
            device_class=NumberDeviceClass.WEIGHT,
            native_unit_of_measurement=UnitOfMass.GRAMS,
            mode=NumberMode.BOX,
        ),
        HCNumberEntityDescription(
            key="number_oven_display_brightness",
            entity=SettingKey.COOKING_OVEN_DISPLAY_BRIGHTNESS,
            entity_category=EntityCategory.CONFIG,
            mode=NumberMode.AUTO,
        ),
        HCNumberEntityDescription(
            key="number_oven_sound_volume",
            entity=SettingKey.COOKING_OVEN_SOUND_VOLUME,
            entity_category=EntityCategory.CONFIG,
            mode=NumberMode.AUTO,
        ),
        # Gaggenau BO470112 and BS474112 report these as Cooking.Common.Setting.* (upstream #513)
        HCNumberEntityDescription(
            key="number_cooking_display_brightness",
            translation_key="number_oven_display_brightness",
            entity=SettingKey.COOKING_COMMON_DISPLAY_BRIGHTNESS,
            entity_category=EntityCategory.CONFIG,
            mode=NumberMode.AUTO,
        ),
        HCNumberEntityDescription(
            key="number_cooking_button_tone_volume",
            entity=SettingKey.COOKING_COMMON_BUTTON_TONE_VOLUME,
            entity_category=EntityCategory.CONFIG,
            mode=NumberMode.AUTO,
        ),
        HCNumberEntityDescription(
            key="number_cooking_signal_volume",
            entity=SettingKey.COOKING_COMMON_SIGNAL_VOLUME,
            entity_category=EntityCategory.CONFIG,
            mode=NumberMode.AUTO,
        ),
        HCNumberEntityDescription(
            key="number_hob_automatic_timer",
            entity=SettingKey.COOKING_HOB_AUTOMATIC_TIMER,
            entity_category=EntityCategory.CONFIG,
            native_max_value=99,  # matching the Home Connect App's limit
            mode=NumberMode.AUTO,
        ),
        HCNumberEntityDescription(
            key="number_hood_interval_off",
            entity=SettingKey.COOKING_HOOD_INTERVAL_TIME_OFF,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            entity_category=EntityCategory.CONFIG,
            mode=NumberMode.AUTO,
        ),
        HCNumberEntityDescription(
            key="number_hood_interval_on",
            entity=SettingKey.COOKING_HOOD_INTERVAL_TIME_ON,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            entity_category=EntityCategory.CONFIG,
            mode=NumberMode.AUTO,
        ),
        HCNumberEntityDescription(
            key="number_hood_delayed_shutoff_time",
            entity=SettingKey.COOKING_HOOD_DELAYED_SHUT_OFF_TIME,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            entity_category=EntityCategory.CONFIG,
            mode=NumberMode.AUTO,
        ),
        HCNumberEntityDescription(
            key="number_hood_sensor_sensitivity",
            entity=SettingKey.COOKING_HOOD_SENSOR_SENSITIVITY,
            mode=NumberMode.AUTO,
        ),
        HCNumberEntityDescription(
            key="number_hood_boost_time",
            entity=SettingKey.COOKING_HOOD_BOOST_TIME,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            entity_category=EntityCategory.CONFIG,
            mode=NumberMode.AUTO,
        ),
    ],
    "select": [
        HCSelectEntityDescription(
            key="select_oven_level",
            entity=OptionKey.COOKING_OVEN_LEVEL,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_oven_clock_display",
            entity=SettingKey.COOKING_OVEN_CLOCK_DISPLAY,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
        ),
        # Display settings of Gaggenau BO470112 and BS474112 (upstream #513)
        HCSelectEntityDescription(
            key="select_oven_idle_screen",
            entity=SettingKey.COOKING_OVEN_IDLE_SCREEN,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSelectEntityDescription(
            key="select_oven_touchkey_color",
            entity=SettingKey.COOKING_OVEN_TOUCHKEY_COLOR,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSelectEntityDescription(
            key="select_oven_standby_display",
            entity=SettingKey.COOKING_OVEN_STANDBY_DISPLAY,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSelectEntityDescription(
            key="select_cooking_button_tone_type",
            entity=SettingKey.COOKING_COMMON_BUTTON_TONE_TYPE,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSelectEntityDescription(
            key="select_oven_used_heating_mode",
            entity=OptionKey.COOKING_OVEN_USED_HEATING_MODE,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_oven_meat_probe_temperature",
            entity=OptionKey.COOKING_OVEN_MEAT_PROBE_TEMPERATURE_V_2,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_pyrolysis_level",
            entity=OptionKey.COOKING_OVEN_PYROLYSIS_LEVEL,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_oven_child_lock_setting",
            entity=SettingKey.COOKING_OVEN_CONFIGURE_CHILD_LOCK,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSelectEntityDescription(
            key="select_oven_switch_on_delay",
            entity=SettingKey.COOKING_OVEN_SWITCH_ON_DELAY,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSelectEntityDescription(
            key="select_oven_cooling_fan_runtime",
            entity=SettingKey.COOKING_OVEN_COOLING_FAN_RUN_ON_TIME,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSelectEntityDescription(
            key="select_oven_signal_duration",
            entity=SettingKey.COOKING_OVEN_SIGNAL_DURATION,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSelectEntityDescription(
            key="select_hob_automatic_keylock",
            entity=SettingKey.COOKING_HOB_AUTOMATIC_KEY_LOCK,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSelectEntityDescription(
            key="select_hob_bridge_zone_mode",
            entity=SettingKey.COOKING_HOB_BRIDGE_ZONE_MODE,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
        ),
        # Cooking.Hob.Option.PowerLevel isn't exposed here - setting it
        # returns 'Error response from Appliance: ReadRequest NotAvailable'.
        HCSelectEntityDescription(
            key="select_hob_hood_automatic_start",
            entity=SettingKey.COOKING_HOB_HOOD_AUTOMATIC_START,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSelectEntityDescription(
            key="select_hob_hood_after_run",
            entity=SettingKey.COOKING_HOB_HOOD_AFTER_RUN,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSelectEntityDescription(
            key="select_hob_ventilation",
            entity=SettingKey.COOKING_HOB_VENTILATION,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSelectEntityDescription(
            key="select_hob_delaye_shutoff_stage",
            entity=SettingKey.COOKING_HOOD_DELAYED_SHUT_OFF_STAGE,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSelectEntityDescription(
            key="select_hob_power_management",
            entity=SettingKey.COOKING_HOB_POWER_MANAGEMENT,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSelectEntityDescription(
            key="select_hob_buzzer_beep_level",
            entity=SettingKey.COOKING_HOB_BUZZER_BEEP_LEVEL,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSelectEntityDescription(
            key="select_hob_end_timer_signal_duration",
            entity=SettingKey.COOKING_HOB_END_TIMER_SIGNALDURATION,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSelectEntityDescription(
            key="select_hood_interval_stage",
            entity=SettingKey.COOKING_HOOD_INTERVAL_STAGE,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSelectEntityDescription(
            key="select_hood_carbon_filter_type",
            entity=SettingKey.COOKING_HOOD_CARBON_FILTER_TYPE,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSelectEntityDescription(
            key="select_hood_color_temperature_mode",
            entity=SettingKey.COOKING_HOOD_COLOR_TEMPERATURE,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSelectEntityDescription(
            key="select_hood_light_startup",
            entity=SettingKey.COOKING_HOOD_WORKING_LIGHT_STARTUP_SETTING,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSelectEntityDescription(
            key="select_hood_light_shutdown",
            entity=SettingKey.COOKING_HOOD_WORKING_LIGHT_SHUTDOWN_SETTING,
            has_state_translation=True,
            entity_category=EntityCategory.CONFIG,
        ),
    ],
    "switch": [
        HCSwitchEntityDescription(
            key="switch_hob_energy_consumption_indication",
            entity=SettingKey.COOKING_HOB_ENERGY_CONSUMPTION_INDICATION,
            device_class=SwitchDeviceClass.SWITCH,
            value_mapping=("IndicationOn", "IndicationOff"),
            entity_category=EntityCategory.CONFIG,
        ),
        HCSwitchEntityDescription(
            key="switch_hob_hood_automatic_light_off",
            entity=SettingKey.COOKING_HOB_HOOD_AUTOMATIC_LIGHT_OFF,
            device_class=SwitchDeviceClass.SWITCH,
            value_mapping=("On", "Off"),
            entity_category=EntityCategory.CONFIG,
        ),
        HCSwitchEntityDescription(
            key="switch_hob_hood_automatic_light_on",
            entity=SettingKey.COOKING_HOB_HOOD_AUTOMATIC_LIGHT_ON,
            device_class=SwitchDeviceClass.SWITCH,
            value_mapping=("On", "Off"),
            entity_category=EntityCategory.CONFIG,
        ),
        HCSwitchEntityDescription(
            key="switch_oven_fast_pre_heat",
            entity=OptionKey.COOKING_OVEN_FAST_PRE_HEAT,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        # Gaggenau BO470112 and BS474112 (upstream #513)
        HCSwitchEntityDescription(
            key="switch_oven_rotary_spit",
            entity=OptionKey.COOKING_OVEN_ROTARY_SPIT,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_oven_quick_roast",
            entity=OptionKey.COOKING_OVEN_QUICK_ROAST,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_oven_heating_signal",
            entity=SettingKey.COOKING_OVEN_HEATING_SIGNAL,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSwitchEntityDescription(
            key="switch_oven_door_opener_delay",
            entity=SettingKey.COOKING_OVEN_DOOR_OPENER_DELAY,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
        ),
        # Gaggenau BO470112 and BS474112 report it as a setting (upstream #513)
        HCSwitchEntityDescription(
            key="switch_oven_fast_pre_heat_setting",
            translation_key="switch_oven_fast_pre_heat",
            entity=SettingKey.COOKING_OVEN_FAST_PRE_HEAT,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_oven_button_tones",
            entity=SettingKey.COOKING_OVEN_BUTTON_TONES,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSwitchEntityDescription(
            key="switch_oven_light_during_operation",
            entity=SettingKey.COOKING_OVEN_OVEN_LIGHT_DURING_OPERATION,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSwitchEntityDescription(
            key="switch_oven_night_dimout",
            entity=SettingKey.COOKING_OVEN_NIGHT_DIMOUT,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSwitchEntityDescription(
            key="switch_oven_sabbath_mode",
            entity=SettingKey.COOKING_OVEN_SABBATH_MODE,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSwitchEntityDescription(
            key="switch_oven_convection_conversion",
            entity=SettingKey.COOKING_OVEN_CONVECTION_CONVERSION,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
        ),
        HCSwitchEntityDescription(
            key="switch_oven_display_standby_dimmed",
            entity=SettingKey.COOKING_OVEN_DISPLAY_STANDBY_DIMMED,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
        ),
        HCSwitchEntityDescription(
            key="switch_oven_teloscopic_slide_out_refited",
            entity=SettingKey.COOKING_OVEN_TELOSCOPIC_SLIDE_OUT_REFITED,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
        ),
        HCSwitchEntityDescription(
            key="switch_oven_display_brand_logo",
            entity=SettingKey.COOKING_OVEN_DISPLAY_BRAND_LOGO,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
        ),
        HCSwitchEntityDescription(
            key="switch_hood_silence_mode",
            entity=SettingKey.COOKING_HOOD_NOISE_REDUCTION,
            device_class=SwitchDeviceClass.SWITCH,
        ),
    ],
    "light": [generate_hood_light, generate_hood_ambient_light, generate_oven_cavity_light],
    "fan": [generate_hood_fan],
    "button": [
        HCButtonEntityDescription(
            key="button_hood_carbon_filter_reset",
            entity=CommandKey.COOKING_COMMON_HOOD_CARBON_FILTER_RESET,
            entity_category=EntityCategory.CONFIG,
        ),
        HCButtonEntityDescription(
            key="button_hood_grease_filter_reset",
            entity=CommandKey.COOKING_COMMON_HOOD_GREASE_FILTER_RESET,
            entity_category=EntityCategory.CONFIG,
        ),
        HCButtonEntityDescription(
            key="button_hood_regenerative_carbon_filter_reset",
            entity=CommandKey.COOKING_COMMON_HOOD_REGENERATIVE_CARBON_FILTER_RESET,
            entity_category=EntityCategory.CONFIG,
        ),
        HCButtonEntityDescription(
            key="button_hood_regenerative_carbon_filter_lifetime_reset",
            entity=CommandKey.COOKING_COMMON_HOOD_REGENERATIVE_CARBON_FILTER_LIFE_TIME_RESET,
            entity_category=EntityCategory.CONFIG,
        ),
    ],
    "binary_sensor": [
        generate_cavity_meatprobe_plugged,
        generate_oven_event,
        generate_meatprobe_plugged,
        # Oven-wide events of Gaggenau BO470112 and BS474112 (upstream #513)
        HCBinarySensorEntityDescription(
            key="binary_sensor_oven_lock_while_cooling_down",
            entity=EventKey.COOKING_OVEN_OVEN_LOCK_WHILE_COOLING_DOWN,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_oven_cavity_temperature_too_high",
            translation_placeholders={"group_name": ""},
            entity=EventKey.COOKING_OVEN_CAVITY_TEMPERATURE_TOO_HIGH,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_category=EntityCategory.DIAGNOSTIC,
            # Feeds the appliance's Problem sensor instead
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_oven_user_interaction_required",
            entity=EventKey.COOKING_OVEN_USER_INTERACTION_REQUIRED,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_oven_cavity_heatup",
            entity=EventKey.COOKING_OVEN_CAVITY_HEATUP,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_oven_operating_time_limit_reached",
            entity=EventKey.COOKING_OVEN_OPERATING_TIME_LIMIT_REACHED,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_oven_cleaning_request",
            entity=EventKey.COOKING_OVEN_CLEANING_REQUEST,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_oven_force_flushing",
            entity=EventKey.COOKING_OVEN_FORCE_FLUSHING,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_oven_descaling_request",
            entity=EventKey.COOKING_OVEN_DESCALING_REQUEST,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_oven_empty_water_container",
            entity=EventKey.COOKING_OVEN_EMPTY_WATER_CONTAINER,
            device_class=BinarySensorDeviceClass.PROBLEM,
            # A refill reminder, like a dishwasher's salt or rinse aid
            in_problem_sensor=False,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_oven_water_supply_closed",
            entity=EventKey.COOKING_OVEN_WATER_SUPPLY_CLOSED,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_category=EntityCategory.DIAGNOSTIC,
            # Feeds the appliance's Problem sensor instead
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_cooking_appliance_module_error",
            entity=EventKey.COOKING_COMMON_APPLIANCE_MODULE_ERROR,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_category=EntityCategory.DIAGNOSTIC,
            # Feeds the appliance's Problem sensor instead
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        # Gaggenau BO470112 and BS474112 (upstream #513)
        HCBinarySensorEntityDescription(
            key="binary_sensor_oven_preheat_finished",
            entity=EventKey.COOKING_COMMON_PREHEAT_FINISHED,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
    ],
}
