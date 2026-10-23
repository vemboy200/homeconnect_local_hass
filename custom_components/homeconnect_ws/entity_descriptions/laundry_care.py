"""Description for LaundryCare Entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from home_disconnect.keys import EventKey, OptionKey, SettingKey, StatusKey
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.components.number import NumberDeviceClass, NumberMode
from homeassistant.components.switch.const import SwitchDeviceClass
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    EntityCategory,
    UnitOfTime,
    UnitOfVolume,
)

from .descriptions_definitions import (
    HCBinarySensorEntityDescription,
    HCLightEntityDescription,
    HCNumberEntityDescription,
    HCSelectEntityDescription,
    HCSwitchEntityDescription,
)

if TYPE_CHECKING:
    from home_disconnect import Appliance

    from .descriptions_definitions import _EntityDescriptionsDefinitionsType


def generate_speed_perfect(appliance: Appliance) -> HCSwitchEntityDescription | None:
    """
    Get the Speed Perfect switch description.

    Washers have it under two names, LaundryCare.Common.Option.SpeedPerfect and
    LaundryCare.Washer.Option.SpeedPerfect, both in the profile. A WGB244A0BY's
    debug log (fork issue #59) only ever used the Common one, but a WGB256ABSN
    profile has a few programs with only the Washer one. So one switch backs
    both and follows whichever the program offers. Keeps each one's own key
    when it's the only one, so existing entities keep their IDs.
    """
    common = OptionKey.LAUNDRY_CARE_COMMON_SPEED_PERFECT
    washer = OptionKey.LAUNDRY_CARE_WASHER_SPEED_PERFECT
    if common in appliance.entities:
        return HCSwitchEntityDescription(
            key="switch_laundry_common_speed_perfect",
            entity=common,
            alternate_entities=(washer,) if washer in appliance.entities else None,
            device_class=SwitchDeviceClass.SWITCH,
            translation_key="switch_laundry_speed_perfect",
        )
    if washer in appliance.entities:
        return HCSwitchEntityDescription(
            key="switch_laundry_speed_perfect",
            entity=washer,
            device_class=SwitchDeviceClass.SWITCH,
        )
    return None


LAUNDRY_ENTITY_DESCRIPTIONS: _EntityDescriptionsDefinitionsType = {
    "binary_sensor": [
        HCBinarySensorEntityDescription(
            key="binary_sensor_refresher_level",
            entity=StatusKey.LAUNDRY_CARE_DRYER_REFRESHER_FILL_LEVEL,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Poor"},
            value_off={"Filled"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_condensate_container_full",
            entity=EventKey.LAUNDRY_CARE_DRYER_CONDENSATE_CONTAINER_FULL,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_lint_filter_full",
            entity=EventKey.LAUNDRY_CARE_DRYER_LINT_FILTER_FULL,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_maintenance_reminder",
            entity=EventKey.LAUNDRY_CARE_DRYER_MAINTENANCE_REMIND,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_drying_process_finished",
            entity=EventKey.LAUNDRY_CARE_DRYER_DRYING_PROCESS_FINISHED,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_cool_down_phase_running",
            entity=EventKey.LAUNDRY_CARE_DRYER_COOL_DOWN_PHASE_RUNNING,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.RUNNING,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_refresher_container_empty",
            entity=EventKey.LAUNDRY_CARE_DRYER_REFRESHER_CONTAINER_EMPTY,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_clean_lint_filter",
            entity=EventKey.LAUNDRY_CARE_DRYER_DRYER_SELF_CLEANING_CLEAN_LINT_FILTER,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_clean_self_cleaning_module",
            entity=EventKey.LAUNDRY_CARE_DRYER_DRYER_SELF_CLEANING_CLEAN_SELF_CLEANING_MODULE,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_easyclean_filter_reminder",
            entity=EventKey.LAUNDRY_CARE_DRYER_EASY_CLEAN_FILTER_REMIND_CLEANING,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_evaporator_frozen",
            entity=EventKey.LAUNDRY_CARE_DRYER_EVAPORATOR_FROZEN,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_foam_detection",
            entity=EventKey.LAUNDRY_CARE_COMMON_FOAM_DETECTION,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_supply_voltage_too_low",
            entity=EventKey.LAUNDRY_CARE_COMMON_SUPPLY_POWER_SUPPLY_VOLTAGE_TOO_LOW,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_water_level_too_high",
            entity=EventKey.LAUNDRY_CARE_COMMON_DOOR_LOCK_WATER_LEVEL_TOO_HIGH,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_door_not_lockable",
            entity=EventKey.LAUNDRY_CARE_COMMON_DOOR_NOT_LOCKABLE,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_door_not_unlockable",
            entity=EventKey.LAUNDRY_CARE_COMMON_DOOR_NOT_UNLOCKABLE,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_fatal_error_occurred",
            entity=EventKey.LAUNDRY_CARE_COMMON_FATAL_ERROR_OCCURED,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_drum_clean_reminder",
            entity=EventKey.LAUNDRY_CARE_WASHER_DRUM_CLEAN_REMINDER,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_idos1_fill_level_poor",
            entity=EventKey.LAUNDRY_CARE_WASHER_I_DOS_1_FILL_LEVEL_POOR,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_idos2_fill_level_poor",
            entity=EventKey.LAUNDRY_CARE_WASHER_I_DOS_2_FILL_LEVEL_POOR,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_idos_unit_defect",
            entity=EventKey.LAUNDRY_CARE_WASHER_I_DOS_UNIT_DEFECT,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_pump_error",
            entity=EventKey.LAUNDRY_CARE_WASHER_PUMP_ERROR,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_spin_abort",
            entity=EventKey.LAUNDRY_CARE_WASHER_SPIN_SPIN_ABORT,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_release_rinse_hold_pending",
            entity=EventKey.LAUNDRY_CARE_WASHER_RELEASE_RINSE_HOLD_PENDING,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_idos_open_tray",
            entity=EventKey.LAUNDRY_CARE_WASHER_I_DOS_I_DOS_OPEN_TRAY,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
    ],
    "select": [
        HCSelectEntityDescription(
            key="select_auto_power_off",
            entity=SettingKey.LAUNDRY_CARE_COMMON_AUTO_POWER_OFF,
            entity_category=EntityCategory.CONFIG,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_brightness",
            entity=SettingKey.LAUNDRY_CARE_COMMON_BRIGHTNESS_LEVEL,
            entity_category=EntityCategory.CONFIG,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_door_light_ring_mode",
            entity=SettingKey.LAUNDRY_CARE_COMMON_DOOR_LIGHT_RING_ACTIVE_MODE,
            entity_category=EntityCategory.CONFIG,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_door_light_ring_brightness",
            entity=SettingKey.LAUNDRY_CARE_COMMON_DOOR_LIGHT_RING_BRIGHTNESS_LEVEL,
            entity_category=EntityCategory.CONFIG,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_end_signal_volume",
            entity=SettingKey.LAUNDRY_CARE_COMMON_END_SIGNAL_VOLUME,
            entity_category=EntityCategory.CONFIG,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_key_signal_volume",
            entity=SettingKey.LAUNDRY_CARE_COMMON_KEY_SIGNAL_VOLUME,
            entity_category=EntityCategory.CONFIG,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_sound_volume",
            entity=SettingKey.LAUNDRY_CARE_COMMON_SOUND_VOLUME,
            entity_category=EntityCategory.CONFIG,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_power_rating",
            entity=SettingKey.LAUNDRY_CARE_COMMON_SUPPLY_POWER_POWER_RATING,
            entity_category=EntityCategory.CONFIG,
            has_state_translation=False,
        ),
        HCSelectEntityDescription(
            key="select_laundry_wrinkle_guard",
            entity=OptionKey.LAUNDRY_CARE_DRYER_WRINKLE_GUARD,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_cupboard_dry_fine_adjust",
            entity=SettingKey.LAUNDRY_CARE_DRYER_CUPBOARD_DRY_FINE_ADJUST,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_cupboard_dry_plus_fine_adjust",
            entity=SettingKey.LAUNDRY_CARE_DRYER_CUPBOARD_DRY_PLUS_FINE_ADJUST,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_iron_dry_fine_adjust",
            entity=SettingKey.LAUNDRY_CARE_DRYER_IRON_DRY_FINE_ADJUST,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_spin_speed_before_drying",
            entity=SettingKey.LAUNDRY_CARE_DRYER_SPIN_SPEED_BEFORE_DRYING,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_drying_target",
            entity=OptionKey.LAUNDRY_CARE_DRYER_DRYING_TARGET,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_washer_dryer_drying_target",
            entity=OptionKey.LAUNDRY_CARE_WASHER_DRYER_DRYING_TARGET,
            # Same values as the dryer's DryingTarget
            translation_key="select_laundry_drying_target",
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_program_mode",
            entity=OptionKey.LAUNDRY_CARE_WASHER_DRYER_PROGRAM_MODE,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_activity_after_washing",
            entity=OptionKey.LAUNDRY_CARE_WASHER_DRYER_ACTIVITY_AFTER_WASHING,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_refresh_intensity",
            entity=OptionKey.LAUNDRY_CARE_WASHER_DRYER_REFRESH_INTENSITY,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_refresh_textile_type",
            entity=OptionKey.LAUNDRY_CARE_WASHER_DRYER_REFRESH_TEXTILE_TYPE,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_refresher",
            entity=OptionKey.LAUNDRY_CARE_DRYER_REFRESHER,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_idos2_content",
            entity=SettingKey.LAUNDRY_CARE_WASHER_I_DOS_2_CONTENT,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_idos2_level",
            entity=OptionKey.LAUNDRY_CARE_WASHER_I_DOS_2_DOSING_LEVEL,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_idos1_level",
            entity=OptionKey.LAUNDRY_CARE_WASHER_I_DOS_1_DOSING_LEVEL,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_vario_perfect",
            entity=OptionKey.LAUNDRY_CARE_COMMON_VARIO_PERFECT,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_hygienic_steam_intensity",
            entity=OptionKey.LAUNDRY_CARE_COMMON_HYGIENIC_STEAM_INTENSITY,
            alternate_entities=(OptionKey.LAUNDRY_CARE_WASHER_HYGIENIC_STEAM_INTENSITY,),
            has_state_translation=True,
        ),
        # The same option, under the Washer name a Bosch WGH24400IT uses
        HCSelectEntityDescription(
            key="select_laundry_pretreatment",
            entity=OptionKey.LAUNDRY_CARE_WASHER_PRE_TREATMENT,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_soak_temperature",
            entity=OptionKey.LAUNDRY_CARE_WASHER_SOAK_TEMPERATURE,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_multiple_soak",
            entity=OptionKey.LAUNDRY_CARE_WASHER_MULTIPLE_SOAK,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_rinseplus",
            entity=OptionKey.LAUNDRY_CARE_WASHER_RINSE_PLUS,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_spin_speed",
            entity=OptionKey.LAUNDRY_CARE_WASHER_SPIN_SPEED,
            has_state_translation=True,
            # Otherwise stays frozen on the last active spin speed (e.g.
            # RPM1400) while the appliance is off, misleadingly implying it's
            # still running - confirmed live on fork issue #7.
            force_option_when_expected_offline="off",
        ),
        HCSelectEntityDescription(
            key="select_laundry_option_stains",
            entity=OptionKey.LAUNDRY_CARE_WASHER_STAINS,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_option_temperature",
            entity=OptionKey.LAUNDRY_CARE_WASHER_TEMPERATURE,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_laundry_option_water_and_rinse_plus",
            entity=OptionKey.LAUNDRY_CARE_WASHER_WATER_AND_RINSE_PLUS,
            has_state_translation=True,
            entity_registry_enabled_default=False,
        ),
    ],
    "number": [
        HCNumberEntityDescription(
            key="number_laundry_brightness",
            entity=SettingKey.LAUNDRY_CARE_COMMON_BRIGHTNESS,
            native_unit_of_measurement=PERCENTAGE,
            entity_category=EntityCategory.CONFIG,
            mode=NumberMode.AUTO,
        ),
        HCNumberEntityDescription(
            key="number_door_light_ring_brightness",
            entity=SettingKey.LAUNDRY_CARE_COMMON_DOOR_LIGHT_RING_BRIGHTNESS,
            native_unit_of_measurement=PERCENTAGE,
            entity_category=EntityCategory.CONFIG,
            mode=NumberMode.AUTO,
        ),
        HCNumberEntityDescription(
            key="number_laundry_soak_duration",
            entity=OptionKey.LAUNDRY_CARE_WASHER_SOAK_DURATION,
            device_class=NumberDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            mode=NumberMode.BOX,
        ),
        HCNumberEntityDescription(
            key="number_laundry_spin_class",
            entity=OptionKey.LAUNDRY_CARE_DRYER_SPIN_CLASS,
            native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
            mode=NumberMode.AUTO,
        ),
        HCNumberEntityDescription(
            key="number_idos1_base_level",
            entity=SettingKey.LAUNDRY_CARE_WASHER_I_DOS_1_BASE_LEVEL,
            entity_category=EntityCategory.CONFIG,
            native_unit_of_measurement=UnitOfVolume.MILLILITERS,
            mode=NumberMode.AUTO,
        ),
        HCNumberEntityDescription(
            key="number_idos2_base_level",
            entity=SettingKey.LAUNDRY_CARE_WASHER_I_DOS_2_BASE_LEVEL,
            entity_category=EntityCategory.CONFIG,
            native_unit_of_measurement=UnitOfVolume.MILLILITERS,
            mode=NumberMode.AUTO,
        ),
    ],
    "switch": [
        HCSwitchEntityDescription(
            key="switch_laundry_end_signal",
            entity=SettingKey.LAUNDRY_CARE_COMMON_END_SIGNAL,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSwitchEntityDescription(
            key="switch_laundry_sound_mute",
            entity=SettingKey.LAUNDRY_CARE_COMMON_SOUND_MUTE,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSwitchEntityDescription(
            key="switch_laundry_time_light",
            entity=SettingKey.LAUNDRY_CARE_COMMON_TIME_LIGHT_ACTIVE,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSwitchEntityDescription(
            key="switch_laundry_wrinkle_guard",
            entity=SettingKey.LAUNDRY_CARE_COMMON_WRINKLE_GUARD,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
        ),
        HCSwitchEntityDescription(
            key="switch_laundry_silent_mode",
            entity=OptionKey.LAUNDRY_CARE_COMMON_SILENT_MODE,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        generate_speed_perfect,
        HCSwitchEntityDescription(
            key="switch_laundry_low_temperature_hygiene",
            entity=OptionKey.LAUNDRY_CARE_COMMON_LOW_TEMPERATURE_HYGIENE,
            alternate_entities=(OptionKey.LAUNDRY_CARE_WASHER_DRYER_LOW_TEMPERATURE_HYGIENE,),
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_laundry_wrinkle_guard_boost",
            entity=OptionKey.LAUNDRY_CARE_WASHER_DRYER_WRINKLE_GUARD_BOOST,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_laundry_gentle",
            entity=OptionKey.LAUNDRY_CARE_DRYER_GENTLE,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_laundry_hygiene",
            entity=OptionKey.LAUNDRY_CARE_DRYER_HYGIENE,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_laundry_idos1_active",
            entity=OptionKey.LAUNDRY_CARE_WASHER_I_DOS_1_ACTIVE,
            alternate_entities=(OptionKey.LAUNDRY_CARE_WASHER_I_DOS_1_ACTIVE_DOTTED,),
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_laundry_idos2_active",
            entity=OptionKey.LAUNDRY_CARE_WASHER_I_DOS_2_ACTIVE,
            alternate_entities=(OptionKey.LAUNDRY_CARE_WASHER_I_DOS_2_ACTIVE_DOTTED,),
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_laundry_intensive_plus",
            entity=OptionKey.LAUNDRY_CARE_WASHER_INTENSIVE_PLUS,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_laundry_mini_load",
            entity=OptionKey.LAUNDRY_CARE_WASHER_MINI_LOAD,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_laundry_less_ironing",
            entity=OptionKey.LAUNDRY_CARE_WASHER_LESS_IRONING,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_laundry_silent_wash",
            entity=OptionKey.LAUNDRY_CARE_WASHER_SILENT_WASH,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_laundry_soak",
            entity=OptionKey.LAUNDRY_CARE_WASHER_SOAK,
            device_class=SwitchDeviceClass.SWITCH,
            entity_registry_enabled_default=False,
        ),
        HCSwitchEntityDescription(
            key="switch_laundry_prewash",
            entity=OptionKey.LAUNDRY_CARE_WASHER_PREWASH,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_laundry_rinse_hold",
            entity=OptionKey.LAUNDRY_CARE_WASHER_RINSE_HOLD,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_laundry_rinse_plus1",
            entity=OptionKey.LAUNDRY_CARE_WASHER_RINSE_PLUS_1,
            device_class=SwitchDeviceClass.SWITCH,
            entity_registry_enabled_default=False,
        ),
        HCSwitchEntityDescription(
            key="switch_laundry_rinse_plus3",
            entity=OptionKey.LAUNDRY_CARE_WASHER_RINSE_PLUS_3,
            device_class=SwitchDeviceClass.SWITCH,
            entity_registry_enabled_default=False,
        ),
        HCSwitchEntityDescription(
            key="switch_laundry_water_and_rinse_plus1",
            entity=OptionKey.LAUNDRY_CARE_WASHER_WATER_AND_RINSE_PLUS_1,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_laundry_water_plus",
            entity=OptionKey.LAUNDRY_CARE_WASHER_WATER_PLUS,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_laundry_disinfectant",
            entity=OptionKey.LAUNDRY_CARE_WASHER_DISINFECTANT,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_laundry_hygienic_steam",
            entity=OptionKey.LAUNDRY_CARE_WASHER_HYGIENIC_STEAM,
            device_class=SwitchDeviceClass.SWITCH,
        ),
    ],
    "light": [
        HCLightEntityDescription(
            key="light_door_ring",
            entity=SettingKey.LAUNDRY_CARE_COMMON_DOOR_LIGHT_RING_ACTIVE,
        ),
        HCLightEntityDescription(
            key="light_drum_light",
            entity=SettingKey.LAUNDRY_CARE_COMMON_DRUM_LIGHT_ACTIVE,
        ),
    ],
}
