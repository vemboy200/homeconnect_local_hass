"""Description for ConsumerProducts Entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from home_disconnect.keys import EventKey, OptionKey, SettingKey
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.components.number import NumberDeviceClass, NumberMode
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.switch.const import SwitchDeviceClass
from homeassistant.const import EntityCategory, UnitOfVolume

from .descriptions_definitions import (
    HCBinarySensorEntityDescription,
    HCNumberEntityDescription,
    HCSelectEntityDescription,
    HCSwitchEntityDescription,
)

if TYPE_CHECKING:
    from .descriptions_definitions import _EntityDescriptionsDefinitionsType

CONSUMER_PRODUCTS_ENTITY_DESCRIPTIONS: _EntityDescriptionsDefinitionsType = {
    "binary_sensor": [
        HCBinarySensorEntityDescription(
            key="binary_sensor_coffee_brewing_unit_missing",
            entity=EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_BREWING_UNIT_IS_MISSING,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_coffee_outlet_missing",
            entity=EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_COFFEE_OUTLET_MISSING,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_coffee_close_door",
            entity=EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_CLOSE_DOOR,
            device_class=BinarySensorDeviceClass.DOOR,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_bean_container_empty",
            entity=EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_BEAN_CONTAINER_EMPTY,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present"},
            value_off={"Off", "Confirmed"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_coffee_cleaning_due",
            entity=EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_DEVICE_SHOULD_BE_CLEANED,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_coffee_calc_n_clean_due",
            entity=EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_DEVICE_SHOULD_BE_CALC_N_CLEANED,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_coffee_clean_brewing_unit",
            entity=EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_CLEAN_BREWING_UNIT,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_coffee_milk_reminder",
            entity=EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_MILK_REMINDER,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_coffee_water_filter_change",
            entity=EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_WATER_FILTER_SHOULD_BE_CHANGED,
            device_class=BinarySensorDeviceClass.PROBLEM,
            in_problem_sensor=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
    ],
    "select": [
        HCSelectEntityDescription(
            key="select_coffee_temperature",
            entity=OptionKey.CONSUMER_PRODUCTS_COFFEE_MAKER_COFFEE_TEMPERATURE,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_bean_amount",
            entity=OptionKey.CONSUMER_PRODUCTS_COFFEE_MAKER_BEAN_AMOUNT,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_beverage_size",
            entity=OptionKey.CONSUMER_PRODUCTS_COFFEE_MAKER_BEVERAGE_SIZE,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_coffee_milk_ratio",
            entity=OptionKey.CONSUMER_PRODUCTS_COFFEE_MAKER_COFFEE_MILK_RATIO,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_hot_water_temperature",
            entity=OptionKey.CONSUMER_PRODUCTS_COFFEE_MAKER_HOT_WATER_TEMPERATURE,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_flow_rate",
            entity=OptionKey.CONSUMER_PRODUCTS_COFFEE_MAKER_FLOW_RATE,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_coarsness",
            entity=OptionKey.CONSUMER_PRODUCTS_COFFEE_MAKER_COARSNESS,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_coffee_strength",
            entity=OptionKey.CONSUMER_PRODUCTS_COFFEE_MAKER_COFFEE_STRENGTH,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_aroma_select",
            entity=OptionKey.CONSUMER_PRODUCTS_COFFEE_MAKER_AROMA_SELECT,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_bean_container",
            entity=OptionKey.CONSUMER_PRODUCTS_COFFEE_MAKER_BEAN_CONTAINER_SELECTION,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_shot_count",
            entity=OptionKey.CONSUMER_PRODUCTS_COFFEE_MAKER_SHOT_COUNT,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_cups",
            entity=OptionKey.CONSUMER_PRODUCTS_COFFEE_MAKER_CUPS,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_coffee_switch_off_after",
            entity=SettingKey.CONSUMER_PRODUCTS_COFFEE_MAKER_SWITCH_OFF_AFTER,
            entity_category=EntityCategory.CONFIG,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_coffee_water_hardness",
            entity=SettingKey.CONSUMER_PRODUCTS_COFFEE_MAKER_WATER_HARDNESS,
            entity_category=EntityCategory.CONFIG,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_coffee_user_mode",
            entity=SettingKey.CONSUMER_PRODUCTS_COFFEE_MAKER_USER_MODE,
            entity_category=EntityCategory.CONFIG,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_coffee_milk_order",
            entity=SettingKey.CONSUMER_PRODUCTS_COFFEE_MAKER_COFFEE_MILK_ORDER,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_coffee_macchiato_pause",
            entity=SettingKey.CONSUMER_PRODUCTS_COFFEE_MAKER_MACCHIATO_PAUSE,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_coffee_milk_reminder",
            entity=SettingKey.CONSUMER_PRODUCTS_COFFEE_MAKER_REMIND_FOR_MILK_AFTER,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_coffee_default_bean_container",
            entity=SettingKey.CONSUMER_PRODUCTS_COFFEE_MAKER_DEFAULT_BEAN_CONTAINER_SELECTION,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
    ],
    "switch": [
        HCSwitchEntityDescription(
            key="switch_multiple_beverages",
            entity=OptionKey.CONSUMER_PRODUCTS_COFFEE_MAKER_MULTIPLE_BEVERAGES,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_cup_warmer",
            entity=SettingKey.CONSUMER_PRODUCTS_COFFEE_MAKER_CUP_WARMER,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_coffee_leave_profiles_automatically",
            entity=SettingKey.CONSUMER_PRODUCTS_COFFEE_MAKER_LEAVE_PROFILES_AUTOMATICALLY,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
        ),
    ],
    "number": [
        HCNumberEntityDescription(
            key="number_fill_quantity",
            entity=OptionKey.CONSUMER_PRODUCTS_COFFEE_MAKER_FILL_QUANTITY,
            device_class=NumberDeviceClass.VOLUME,
            native_unit_of_measurement=UnitOfVolume.MILLILITERS,
            mode=NumberMode.BOX,
        ),
        HCNumberEntityDescription(
            key="number_coffee_display_brightness",
            entity=SettingKey.CONSUMER_PRODUCTS_COFFEE_MAKER_BRIGHTNESS_DISPLAY,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            mode=NumberMode.AUTO,
        ),
    ],
}
