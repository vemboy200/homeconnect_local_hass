"""Description for Dishcare.Dishwasher Entities."""

from __future__ import annotations

from home_disconnect.keys import EventKey, OptionKey, SettingKey, StatusKey
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.components.switch.const import SwitchDeviceClass
from homeassistant.const import EntityCategory

from .descriptions_definitions import (
    HCBinarySensorEntityDescription,
    HCSelectEntityDescription,
    HCSwitchEntityDescription,
    _EntityDescriptionsDefinitionsType,
)

DISHCARE_ENTITY_DESCRIPTIONS: _EntityDescriptionsDefinitionsType = {
    "binary_sensor": [
        HCBinarySensorEntityDescription(
            key="binary_sensor_eco_dry_active",
            entity=StatusKey.DISHCARE_DISHWASHER_ECO_DRY_ACTIVE,
            entity_registry_enabled_default=False,
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_machinecarereminder",
            entity=EventKey.DISHCARE_DISHWASHER_MACHINE_CARE_REMINDER,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_low_voltage",
            entity=EventKey.DISHCARE_DISHWASHER_LOW_VOLTAGE,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_machinecareandfiltercleaningreminder",
            entity=EventKey.DISHCARE_DISHWASHER_MACHINE_CARE_AND_FILTER_CLEANING_REMINDER,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_waterheatercalcified",
            entity=EventKey.DISHCARE_DISHWASHER_WATERHEATER_CALCIFIED,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_smartfiltercleaningreminder",
            entity=EventKey.DISHCARE_DISHWASHER_SMART_FILTER_CLEANING_REMINDER,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_checkfiltersystem",
            entity=EventKey.DISHCARE_DISHWASHER_CHECK_FILTER_SYSTEM,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_drainingnotpossible",
            translation_key="binary_sensor_draining_not_possible",
            entity=EventKey.DISHCARE_DISHWASHER_DRAINING_NOT_POSSIBLE,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_drainpumpblocked",
            translation_key="binary_sensor_drain_pump_blocked",
            entity=EventKey.DISHCARE_DISHWASHER_DRAIN_PUMP_BLOCKED,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        # FlexSpray error events
        # NOTE: Bosch refers to this feature as "PowerControl" in marketing/UI.
        # The protocol/API objects use the name "FlexSpray", which is kept here.
        HCBinarySensorEntityDescription(
            key="binary_sensor_flexspray_error_blocked",
            entity=EventKey.DISHCARE_DISHWASHER_FLEX_SPRAY_ERROR_BLOCKED,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_flexspray_error_general",
            entity=EventKey.DISHCARE_DISHWASHER_FLEX_SPRAY_ERROR_GENERAL,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_flexspray_error_spray_arm_not_mounted",
            entity=EventKey.DISHCARE_DISHWASHER_FLEX_SPRAY_ERROR_SPRAY_ARM_NOT_MOUNTED,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
    ],
    "select": [
        HCSelectEntityDescription(
            key="select_drying_assistant_all_programs",
            entity=SettingKey.DISHCARE_DISHWASHER_DRYING_ASSISTANT_ALL_PROGRAMS,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_hot_water",
            entity=SettingKey.DISHCARE_DISHWASHER_HOT_WATER,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_rinse_aid",
            entity=SettingKey.DISHCARE_DISHWASHER_RINSE_AID,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_sound_level_signal",
            entity=SettingKey.DISHCARE_DISHWASHER_SOUND_LEVEL_SIGNAL,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_sound_level_key",
            entity=SettingKey.DISHCARE_DISHWASHER_SOUND_LEVEL_KEY,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_water_hardness",
            entity=SettingKey.DISHCARE_DISHWASHER_WATER_HARDNESS,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_sensitivity_turbidity",
            entity=SettingKey.DISHCARE_DISHWASHER_SENSITIVITY_TURBIDITY,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_eco_as_default",
            entity=SettingKey.DISHCARE_DISHWASHER_ECO_AS_DEFAULT,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_dishwasher_auto_power_off",
            entity=SettingKey.DISHCARE_DISHWASHER_AUTO_POWER_OFF,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        # FlexSpray configuration options
        # NOTE: Bosch refers to this feature as "PowerControl" in marketing/UI.
        # The protocol/API objects use the name "FlexSpray", which is kept here.
        HCSelectEntityDescription(
            key="select_flexspray_type",
            entity=OptionKey.DISHCARE_DISHWASHER_FLEX_SPRAY_TYPE,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_flexspray_front_left",
            entity=OptionKey.DISHCARE_DISHWASHER_FLEX_SPRAY_FRONT_LEFT,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_flexspray_back_left",
            entity=OptionKey.DISHCARE_DISHWASHER_FLEX_SPRAY_BACK_LEFT,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_flexspray_back_right",
            entity=OptionKey.DISHCARE_DISHWASHER_FLEX_SPRAY_BACK_RIGHT,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_flexspray_front_right",
            entity=OptionKey.DISHCARE_DISHWASHER_FLEX_SPRAY_FRONT_RIGHT,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        # FlexSpray custom settings
        HCSelectEntityDescription(
            key="select_flexspray_custom_front_left",
            entity=SettingKey.DISHCARE_DISHWASHER_FLEX_SPRAY_CUSTOM_FRONT_LEFT,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_flexspray_custom_back_left",
            entity=SettingKey.DISHCARE_DISHWASHER_FLEX_SPRAY_CUSTOM_BACK_LEFT,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_flexspray_custom_back_right",
            entity=SettingKey.DISHCARE_DISHWASHER_FLEX_SPRAY_CUSTOM_BACK_RIGHT,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_flexspray_custom_front_right",
            entity=SettingKey.DISHCARE_DISHWASHER_FLEX_SPRAY_CUSTOM_FRONT_RIGHT,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
    ],
    "switch": [
        HCSwitchEntityDescription(
            key="switch_extra_dry_option",
            entity=OptionKey.DISHCARE_DISHWASHER_EXTRA_DRY,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_hygiene_plus",
            entity=OptionKey.DISHCARE_DISHWASHER_HYGIENE_PLUS,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_intensiv_zone",
            entity=OptionKey.DISHCARE_DISHWASHER_INTENSIV_ZONE,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_vario_speed_plus",
            entity=OptionKey.DISHCARE_DISHWASHER_VARIO_SPEED_PLUS,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_silence_on_demand",
            entity=OptionKey.DISHCARE_DISHWASHER_SILENCE_ON_DEMAND,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_brilliance_dry",
            entity=OptionKey.DISHCARE_DISHWASHER_BRILLIANCE_DRY,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        # Also referred to as "CrystalDry"
        HCSwitchEntityDescription(
            key="switch_zeolite_dry",
            entity=OptionKey.DISHCARE_DISHWASHER_ZEOLITE_DRY,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
        ),
        # Also referred to as "EfficientDry"
        HCSwitchEntityDescription(
            key="switch_eco_dry_option",
            entity=OptionKey.DISHCARE_DISHWASHER_ECO_DRY,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_extra_dry",
            entity=SettingKey.DISHCARE_DISHWASHER_EXTRA_DRY,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
        ),
        HCSwitchEntityDescription(
            key="switch_speed_on_demand",
            entity=SettingKey.DISHCARE_DISHWASHER_SPEED_ON_DEMAND,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
        ),
        HCSwitchEntityDescription(
            key="switch_info_light",
            entity=SettingKey.DISHCARE_DISHWASHER_INFO_LIGHT,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
        ),
        HCSwitchEntityDescription(
            key="switch_extra_rinse",
            entity=OptionKey.DISHCARE_DISHWASHER_EXTRA_RINSE,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_dishwasher_sanitation",
            entity=OptionKey.DISHCARE_DISHWASHER_SANITATION_UC,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        # Bosch/Siemens call this "TimeLight" (projects remaining time on the floor).
        HCSwitchEntityDescription(
            key="switch_dishwasher_time_light",
            entity=SettingKey.DISHCARE_DISHWASHER_TIME_LIGHT,
            device_class=SwitchDeviceClass.SWITCH,
            value_mapping=("On", "Off"),
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
        ),
        HCSwitchEntityDescription(
            key="switch_pretreatment",
            entity=OptionKey.DISHCARE_DISHWASHER_PRETREATMENT,
            device_class=SwitchDeviceClass.SWITCH,
        ),
    ],
}
