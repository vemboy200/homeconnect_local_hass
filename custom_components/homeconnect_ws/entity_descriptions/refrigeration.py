"""Description for Cooking Entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from home_disconnect.entities import Access
from home_disconnect.keys import CommandKey, EventKey, SettingKey, StatusKey
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.components.number import NumberDeviceClass, NumberMode
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.components.switch.const import SwitchDeviceClass
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature, UnitOfTime

from .descriptions_definitions import (
    HCBinarySensorEntityDescription,
    HCButtonEntityDescription,
    HCLightEntityDescription,
    HCNumberEntityDescription,
    HCSelectEntityDescription,
    HCSensorEntityDescription,
    HCSwitchEntityDescription,
    _EntityDescriptionsDefinitionsType,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from home_disconnect import Appliance


_INTERNAL_LIGHT_POWER = SettingKey.REFRIGERATION_COMMON_LIGHT_INTERNAL_POWER
_INTERNAL_LIGHT_BRIGHTNESS = SettingKey.REFRIGERATION_COMMON_LIGHT_INTERNAL_BRIGHTNESS


def _has_internal_light(appliance: Appliance) -> bool:
    """
    Whether the interior light can be switched.

    Some appliances list its power as fixed (Access.READ_STATIC, e.g. a Thermador
    T36IF905SP freezer): the light just comes on with the door, and a light
    entity for it could never be used.
    """
    power = appliance.entities.get(_INTERNAL_LIGHT_POWER)
    return power is not None and power.access is not Access.READ_STATIC


def generate_internal_light(appliance: Appliance) -> HCLightEntityDescription | None:
    """Get internal light description."""
    if not _has_internal_light(appliance):
        return None
    brightness = _INTERNAL_LIGHT_BRIGHTNESS
    return HCLightEntityDescription(
        key="light_internal",
        entity=_INTERNAL_LIGHT_POWER,
        brightness_entity=brightness if brightness in appliance.entities else None,
    )


def generate_internal_light_brightness(
    appliance: Appliance,
) -> HCNumberEntityDescription | None:
    """Get internal light brightness description."""
    if _INTERNAL_LIGHT_BRIGHTNESS not in appliance.entities:
        return None

    return HCNumberEntityDescription(
        key="number_light_internal_brightness",
        entity=_INTERNAL_LIGHT_BRIGHTNESS,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.AUTO,
        native_step=1,
        # The light entity already exposes brightness, so this would be a
        # second control for the same setting.
        entity_registry_enabled_default=not _has_internal_light(appliance),
    )


# Per-compartment door sensors, in both naming schemes. The chiller's count
# as a compartment here, but always get their (disabled by default) entity.
_COMPARTMENT_DOORS = (
    StatusKey.REFRIGERATION_COMMON_DOOR_FREEZER,
    StatusKey.REFRIGERATION_COMMON_DOOR_REFRIGERATOR,
    StatusKey.REFRIGERATION_COMMON_DOOR_CHILLER_COMMON,
    StatusKey.REFRIGERATION_FRIDGE_FREEZER_DOOR_FREEZER,
    StatusKey.REFRIGERATION_FRIDGE_FREEZER_DOOR_REFRIGERATOR,
    StatusKey.REFRIGERATION_FRIDGE_FREEZER_CHILLER_COMMON,
)


def compartment_door(
    key: str, entity: str
) -> Callable[[Appliance], HCBinarySensorEntityDescription | None]:
    """
    Get a compartment door description, unless it's the appliance's only door.

    A freezer or fridge with one door reports it both as the compartment's door
    and as BSH.Common.Status.DoorState, which already gets a Door entity (see
    generate_door_binary_sensor). The compartment door only tells doors apart when the
    appliance has more than one.
    """

    def generate(appliance: Appliance) -> HCBinarySensorEntityDescription | None:
        compartments = [door for door in _COMPARTMENT_DOORS if door in appliance.entities]
        if compartments == [entity] and StatusKey.BSH_COMMON_DOOR_STATE in appliance.entities:
            return None
        return HCBinarySensorEntityDescription(
            key=key,
            entity=entity,
            device_class=BinarySensorDeviceClass.DOOR,
            value_on={"Open"},
            value_off={"Closed"},
        )

    return generate


REFRIGERATION_ENTITY_DESCRIPTIONS: _EntityDescriptionsDefinitionsType = {
    "binary_sensor": [
        HCBinarySensorEntityDescription(
            key="binary_sensor_chiller_common_door_state",
            entity=StatusKey.REFRIGERATION_COMMON_DOOR_CHILLER_COMMON,
            alternate_entities=(StatusKey.REFRIGERATION_FRIDGE_FREEZER_CHILLER_COMMON,),
            device_class=BinarySensorDeviceClass.DOOR,
            entity_registry_enabled_default=False,
            value_on={"Open"},
            value_off={"Closed"},
        ),
        compartment_door(
            "binary_sensor_freezer_door_state", StatusKey.REFRIGERATION_COMMON_DOOR_FREEZER
        ),
        compartment_door(
            "binary_sensor_fridge_door_state", StatusKey.REFRIGERATION_COMMON_DOOR_REFRIGERATOR
        ),
        compartment_door(
            "binary_sensor_freezer_door_state", StatusKey.REFRIGERATION_FRIDGE_FREEZER_DOOR_FREEZER
        ),
        compartment_door(
            "binary_sensor_fridge_door_state",
            StatusKey.REFRIGERATION_FRIDGE_FREEZER_DOOR_REFRIGERATOR,
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_door_alarm_chiller_common",
            entity=EventKey.REFRIGERATION_FRIDGE_FREEZER_DOOR_ALARM_CHILLER_COMMON,
            alternate_entities=(EventKey.REFRIGERATION_COMMON_DOOR_ALARM_CHILLER_COMMON,),
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_door_alarm_freezer",
            entity=EventKey.REFRIGERATION_FRIDGE_FREEZER_DOOR_ALARM_FREEZER,
            alternate_entities=(EventKey.REFRIGERATION_COMMON_DOOR_ALARM_FREEZER,),
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_door_alarm_fridge",
            entity=EventKey.REFRIGERATION_FRIDGE_FREEZER_DOOR_ALARM_REFRIGERATOR,
            alternate_entities=(EventKey.REFRIGERATION_COMMON_DOOR_ALARM_REFRIGERATOR,),
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_temperature_alarm_freezer",
            entity=EventKey.REFRIGERATION_FRIDGE_FREEZER_TEMPERATURE_ALARM_FREEZER,
            alternate_entities=(EventKey.REFRIGERATION_COMMON_FREEZER_TEMPERATURE_ALARM,),
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_refrigerator_defrost",
            entity=StatusKey.REFRIGERATION_COMMON_FREEZER_DEFROST,
            alternate_entities=(StatusKey.REFRIGERATION_FRIDGE_FREEZER_DEFROST_FREEZER,),
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_water_filter_full",
            entity=EventKey.REFRIGERATION_COMMON_DISPENSER_WATER_FILTER_FULL,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_freezer_appliance_error",
            entity=EventKey.REFRIGERATION_FRIDGE_FREEZER_APPLIANCE_ERROR,
            alternate_entities=(EventKey.REFRIGERATION_COMMON_APPLIANCE_ERROR,),
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_freezer_low_voltage",
            entity=EventKey.REFRIGERATION_FRIDGE_FREEZER_LOW_VOLTAGE_HINT,
            alternate_entities=(EventKey.REFRIGERATION_COMMON_LOW_VOLTAGE_HINT,),
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_temperature_alarm_chiller_common",
            entity=EventKey.REFRIGERATION_COMMON_CHILLER_COMMON_TEMPERATURE_ALARM,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_ice_hopper_full",
            entity=StatusKey.REFRIGERATION_COMMON_DISPENSER_ICE_HOPPER_FULL,
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_water_filter_almost_full",
            entity=EventKey.REFRIGERATION_COMMON_DISPENSER_WATER_FILTER_ALMOST_FULL,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_ice_expired",
            entity=EventKey.REFRIGERATION_COMMON_DISPENSER_ICE_EXPIRED,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_water_expired",
            entity=EventKey.REFRIGERATION_COMMON_WATER_EXPIRED,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_party_mode_empty_ice_hopper",
            entity=EventKey.REFRIGERATION_COMMON_DISPENSER_PARTY_MODE_EMPTY_ICE_HOPPER,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
    ],
    "button": [
        HCButtonEntityDescription(
            key="button_water_filter_reset",
            entity=CommandKey.REFRIGERATION_COMMON_DISPENSER_WATER_FILTER_RESET,
            entity_category=EntityCategory.CONFIG,
        ),
        HCButtonEntityDescription(
            key="button_refrigerator_open_door",
            entity=CommandKey.BSH_COMMON_OPEN_DOOR,
            entity_registry_enabled_default=False,
        ),
    ],
    "sensor": [
        HCSensorEntityDescription(
            key="sensor_water_filter_saturation",
            entity=StatusKey.REFRIGERATION_COMMON_DISPENSER_WATER_FILTER_SATURATION,
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        HCSensorEntityDescription(
            key="sensor_temperature_ambient",
            entity=StatusKey.REFRIGERATION_FRIDGE_FREEZER_TEMPERATURE_AMBIENT,
            alternate_entities=(StatusKey.REFRIGERATION_COMMON_TEMPERATURE_AMBIENT,),
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        HCSensorEntityDescription(
            key="sensor_temperature_memory_freezer",
            entity=StatusKey.REFRIGERATION_COMMON_FREEZER_MEMORY_TEMPERATURE,
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            entity_registry_enabled_default=False,
        ),
    ],
    "number": [
        HCNumberEntityDescription(
            key="number_setpoint_freezer",
            entity=SettingKey.REFRIGERATION_FRIDGE_FREEZER_SETPOINT_TEMPERATURE_FREEZER,
            alternate_entities=(SettingKey.REFRIGERATION_COMMON_FREEZER_SETPOINT_TEMPERATURE,),
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=NumberDeviceClass.TEMPERATURE,
            mode=NumberMode.AUTO,
            native_step=1,
        ),
        HCNumberEntityDescription(
            key="number_setpoint_refrigerator",
            entity=SettingKey.REFRIGERATION_FRIDGE_FREEZER_SETPOINT_TEMPERATURE_REFRIGERATOR,
            alternate_entities=(SettingKey.REFRIGERATION_COMMON_REFRIGERATOR_SETPOINT_TEMPERATURE,),
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=NumberDeviceClass.TEMPERATURE,
            mode=NumberMode.AUTO,
            native_step=1,
        ),
        HCNumberEntityDescription(
            key="number_setpoint_freezer_fahrenheit",
            translation_key="number_setpoint_freezer",
            entity=SettingKey.REFRIGERATION_COMMON_FREEZER_SETPOINT_TEMPERATURE_FAHRENHEIT,
            native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
            device_class=NumberDeviceClass.TEMPERATURE,
            mode=NumberMode.AUTO,
            native_step=1,
        ),
        HCNumberEntityDescription(
            key="number_setpoint_refrigerator_fahrenheit",
            translation_key="number_setpoint_refrigerator",
            entity=SettingKey.REFRIGERATION_COMMON_REFRIGERATOR_SETPOINT_TEMPERATURE_FAHRENHEIT,
            native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
            device_class=NumberDeviceClass.TEMPERATURE,
            mode=NumberMode.AUTO,
            native_step=1,
        ),
        # This is only available when the `ChillerCommon.Preset` is `custom`.
        HCNumberEntityDescription(
            key="number_setpoint_chiller_common",
            entity=SettingKey.REFRIGERATION_COMMON_CHILLER_COMMON_SETPOINT_TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=NumberDeviceClass.TEMPERATURE,
            entity_registry_enabled_default=False,
            mode=NumberMode.AUTO,
            native_step=1,
        ),
        # This is only available when the `ChillerCommon.Preset` is `custom`.
        HCNumberEntityDescription(
            key="number_setpoint_chiller_common_fahrenheit",
            translation_key="number_setpoint_chiller_common",
            entity=SettingKey.REFRIGERATION_COMMON_CHILLER_COMMON_SETPOINT_TEMPERATURE_FAHRENHEIT,
            native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
            device_class=NumberDeviceClass.TEMPERATURE,
            entity_registry_enabled_default=False,
            mode=NumberMode.AUTO,
            native_step=1,
        ),
        generate_internal_light_brightness,
        HCNumberEntityDescription(
            key="number_refrigerator_door_assistant_freezer_timeout",
            entity=SettingKey.REFRIGERATION_COMMON_DOOR_ASSISTANT_TIMEOUT_FREEZER,
            device_class=NumberDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            mode=NumberMode.AUTO,
        ),
        HCNumberEntityDescription(
            key="number_refrigerator_door_assistant_fridge_timeout",
            entity=SettingKey.REFRIGERATION_COMMON_DOOR_ASSISTANT_TIMEOUT_FRIDGE,
            device_class=NumberDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            mode=NumberMode.AUTO,
        ),
        HCNumberEntityDescription(
            key="number_refrigerator_sabbath_mode_duration",
            entity=SettingKey.REFRIGERATION_COMMON_SABBATH_MODE_DURATION,
            device_class=NumberDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            entity_category=EntityCategory.CONFIG,
            mode=NumberMode.BOX,
        ),
    ],
    "switch": [
        HCSwitchEntityDescription(
            key="switch_super_freezer",
            entity=SettingKey.REFRIGERATION_FRIDGE_FREEZER_SUPER_MODE_FREEZER,
            alternate_entities=(SettingKey.REFRIGERATION_COMMON_FREEZER_SUPER_MODE,),
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_super_refrigerator",
            entity=SettingKey.REFRIGERATION_FRIDGE_FREEZER_SUPER_MODE_REFRIGERATOR,
            alternate_entities=(SettingKey.REFRIGERATION_COMMON_REFRIGERATOR_SUPER_MODE,),
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_refrigerator_eco",
            entity=SettingKey.REFRIGERATION_FRIDGE_FREEZER_ECO_MODE,
            alternate_entities=(SettingKey.REFRIGERATION_COMMON_ECO_MODE,),
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_refrigerator_vacation",
            entity=SettingKey.REFRIGERATION_FRIDGE_FREEZER_VACATION_MODE,
            alternate_entities=(SettingKey.REFRIGERATION_COMMON_VACATION_MODE,),
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_refrigerator_dispenser_enabled",
            entity=SettingKey.REFRIGERATION_COMMON_DISPENSER_ENABLED,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_refrigerator_dispenser_party_mode",
            entity=SettingKey.REFRIGERATION_COMMON_DISPENSER_PARTY_MODE,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_refrigerator_sabbath_mode",
            entity=SettingKey.REFRIGERATION_COMMON_SABBATH_MODE,
            alternate_entities=(SettingKey.REFRIGERATION_FRIDGE_FREEZER_SABBATH_MODE,),
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSwitchEntityDescription(
            key="switch_refrigerator_door_assistant_freezer",
            entity=SettingKey.REFRIGERATION_COMMON_DOOR_ASSISTANT_FREEZER,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSwitchEntityDescription(
            key="switch_refrigerator_door_assistant_fridge",
            entity=SettingKey.REFRIGERATION_COMMON_DOOR_ASSISTANT_FRIDGE,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSwitchEntityDescription(
            key="switch_refrigeration_light_theater_mode",
            entity=SettingKey.REFRIGERATION_COMMON_LIGHT_INTERNAL_ENABLE_THEATER_MODE,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_refrigerator_fresh_mode",
            entity=SettingKey.REFRIGERATION_FRIDGE_FREEZER_FRESH_MODE,
            alternate_entities=(SettingKey.REFRIGERATION_COMMON_FRESH_MODE,),
            device_class=SwitchDeviceClass.SWITCH,
        ),
    ],
    "select": [
        HCSelectEntityDescription(
            key="select_refrigerator_door_assistant_freezer_trigger",
            entity=SettingKey.REFRIGERATION_COMMON_DOOR_ASSISTANT_TRIGGER_FREEZER,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_refrigerator_door_assistant_freezer_force",
            entity=SettingKey.REFRIGERATION_COMMON_DOOR_ASSISTANT_FORCE_FREEZER,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_refrigerator_door_assistant_fridge_trigger",
            entity=SettingKey.REFRIGERATION_COMMON_DOOR_ASSISTANT_TRIGGER_FRIDGE,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_refrigerator_door_assistant_fridge_force",
            entity=SettingKey.REFRIGERATION_COMMON_DOOR_ASSISTANT_FORCE_FRIDGE,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_chiller_common_preset",
            entity=SettingKey.REFRIGERATION_COMMON_CHILLER_COMMON_PRESET,
            device_class=SensorDeviceClass.ENUM,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        # This is only available when the `ChillerCommon.Preset` is `custom`.
        HCSelectEntityDescription(
            key="select_chiller_left_humidity",
            entity=SettingKey.REFRIGERATION_COMMON_CHILLER_LEFT_HUMIDITY,
            device_class=SensorDeviceClass.ENUM,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        # This is only available when the `ChillerCommon.Preset` is `custom`.
        HCSelectEntityDescription(
            key="select_chiller_right_humidity",
            entity=SettingKey.REFRIGERATION_COMMON_CHILLER_RIGHT_HUMIDITY,
            device_class=SensorDeviceClass.ENUM,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
    ],
    "light": [
        generate_internal_light,
        HCLightEntityDescription(
            key="light_logo",
            entity=SettingKey.REFRIGERATION_COMMON_LIGHT_LOGO_POWER,
            entity_category=EntityCategory.CONFIG,
        ),
    ],
}
