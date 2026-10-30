"""Sensor entities."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any, ClassVar, cast

from home_disconnect.entities import Access, Program
from home_disconnect.keys import EventKey, OptionKey, RootKey, StatusKey
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfEnergy,
    UnitOfMass,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
)

from .entity import HCEntity
from .entity_descriptions.common import door_state_count, program_names
from .entity_descriptions.cooking import oven_status_cavities
from .entity_descriptions.descriptions_definitions import (
    HCBinarySensorEntityDescription,
    HCSensorEntityDescription,
    _EntityDescriptionsDefinitionsType,
    keep_known_events,
)
from .helpers import binary_is_on, create_entities, entity_is_available

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable

    from home_disconnect import Appliance
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback
    from homeassistant.helpers.typing import StateType

    from . import HCConfigEntry, HCData

PARALLEL_UPDATES = 0

_OPERATION_STATE_ENTITY = StatusKey.BSH_COMMON_OPERATION_STATE
_ACTIVE_PROGRAM_ENTITY = RootKey.BSH_COMMON_ACTIVE_PROGRAM
_REMAINING_PROGRAM_TIME_ENTITY = OptionKey.BSH_COMMON_REMAINING_PROGRAM_TIME
# The operation states core home_connect's program sensors are available in
_PROGRAM_OPERATION_STATES = ("DelayedStart", "Run", "Pause", "Finished")


def _program_running(appliance: Appliance) -> bool:
    """Whether a program is delayed, running, paused or finished."""
    operation_state = appliance.entities.get(_OPERATION_STATE_ENTITY)
    return operation_state is not None and operation_state.value in _PROGRAM_OPERATION_STATES


# HCWiFI and the ipv4/ipv6 address sensors are the only should_poll entities in
# this platform, so this interval only affects them. Their /ni/info data is only
# available via an active request (there's no push notification for any of it),
# and the appliance is stationary, so none of it has reason to change minute-to-
# minute. Poll infrequently: enough to catch a real change/degradation trend,
# without adding needless traffic to the appliance's connection. All three share
# one fetch per interval rather than issuing three - see
# coordinator.async_get_network_info.
SCAN_INTERVAL = timedelta(hours=1)

# (exclusive upper bound on |RSSI| in dBm, icon) - checked in order, first match wins.
# WiFi typically drops the connection entirely around -90 dBm, so a reading that
# weak while still connected is either about to drop or already unreliable.
_WIFI_STRENGTH_ICONS = (
    (60, "mdi:wifi-strength-4"),
    (70, "mdi:wifi-strength-3"),
    (80, "mdi:wifi-strength-2"),
    (90, "mdi:wifi-strength-1"),
)


# Entity descriptions


def generate_door_sensor(appliance: Appliance) -> HCSensorEntityDescription | None:
    """Get the Door sensor description, for a door with more than two states."""
    count = door_state_count(appliance)
    if count is None or count <= 2:
        return None
    return HCSensorEntityDescription(
        key="sensor_door_state",
        entity=StatusKey.BSH_COMMON_DOOR_STATE,
        device_class=SensorDeviceClass.ENUM,
        has_state_translation=True,
    )


def generate_active_program(appliance: Appliance) -> HCSensorEntityDescription | None:
    """Get the Active program sensor description."""
    if not (programs := program_names(appliance)):
        return None
    return HCSensorEntityDescription(
        key="sensor_active_program",
        entity=RootKey.BSH_COMMON_ACTIVE_PROGRAM,
        device_class=SensorDeviceClass.ENUM,
        has_state_translation=False,
        mapping=programs,
        clear_on_expected_offline=True,
    )


PROGRAM_SESSION_SUMMARY = StatusKey.BSH_COMMON_PROGRAM_SESSION_SUMMARY_LATEST


ENERGY_CONSUMED_LAST = StatusKey.BSH_COMMON_PROGRAM_LAST_ENERGY_CONSUMED


WATER_CONSUMED_LAST = StatusKey.BSH_COMMON_PROGRAM_LAST_WATER_CONSUMED


def session_summary_detail(appliance: Appliance, uid: int) -> object:
    """Get a value from the details of the latest Program Session Summary."""
    summary = appliance.entities.get(PROGRAM_SESSION_SUMMARY)
    if summary is None or not isinstance(summary.value, dict):
        return None
    for run in reversed(summary.value.get("sequence", [])):
        for detail in run.get("details", []):
            if detail.get("uid") == uid:
                return detail.get("value")
    return None


def last_program_value(appliance: Appliance, name: str) -> float | None:
    """
    Get the value of a Program.Last status.

    Falls back to the latest Program Session Summary: a Bosch WGH24400IT
    washer leaves the Program.Last statuses empty after reconnecting, while
    the summary still lists them.
    """
    status = appliance.entities[name]
    value = status.value
    if value is None:
        value = session_summary_detail(appliance, status.uid)
    return value if isinstance(value, int | float) else None


def generate_last_program_consumption(appliance: Appliance) -> list[HCSensorEntityDescription]:
    """
    Get the energy and water consumption of the last program.

    When the appliance has a Program Session Summary, the sensors follow it
    instead of the Program.Last status, so they still get a value while the
    status is empty, and they listen to the status too.
    """
    descriptions: list[HCSensorEntityDescription] = []
    summary = PROGRAM_SESSION_SUMMARY if PROGRAM_SESSION_SUMMARY in appliance.entities else None

    def value_fn(name: str, scale: int = 1) -> Callable[[StateType], StateType]:
        def read(_: StateType) -> StateType:
            value = last_program_value(appliance, name)
            return None if value is None else value / scale

        return read

    if ENERGY_CONSUMED_LAST in appliance.entities:
        descriptions.append(
            HCSensorEntityDescription(
                key="sensor_energy_consumed_last",
                entity=summary or ENERGY_CONSUMED_LAST,
                entities=[ENERGY_CONSUMED_LAST] if summary else None,
                device_class=SensorDeviceClass.ENERGY,
                native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
                suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                value_fn=value_fn(ENERGY_CONSUMED_LAST),
            )
        )
    if WATER_CONSUMED_LAST in appliance.entities:
        descriptions.append(
            HCSensorEntityDescription(
                key="sensor_water_consumed_last",
                entity=summary or WATER_CONSUMED_LAST,
                entities=[WATER_CONSUMED_LAST] if summary else None,
                device_class=SensorDeviceClass.WATER,
                native_unit_of_measurement=UnitOfVolume.LITERS,
                # Reported in mL, which the water device class doesn't take
                value_fn=value_fn(WATER_CONSUMED_LAST, scale=1000),
            )
        )
    return descriptions


def generate_wifi(appliance: Appliance) -> HCSensorEntityDescription:  # noqa: ARG001
    """
    Get WiFi sensor description.

    Always uses the polling HCWiFI sensor (queries /ni/info directly) rather than
    the appliance's BSH.Common.Status.WiFiSignalStrength status entity: that status
    is only ever populated once at connect and is never pushed again afterward, so
    it goes permanently stale until the next reconnect.
    """
    return HCSensorEntityDescription(
        key="sensor_wifi_signal_strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    )


def generate_ipv4(appliance: Appliance) -> HCSensorEntityDescription:  # noqa: ARG001
    """Get IPv4 address sensor description. Polled the same way as generate_wifi."""
    return HCSensorEntityDescription(
        key="sensor_ipv4_address",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    )


def generate_ipv6(appliance: Appliance) -> HCSensorEntityDescription:  # noqa: ARG001
    """Get IPv6 address sensor description. Polled the same way as generate_wifi."""
    return HCSensorEntityDescription(
        key="sensor_ipv6_address",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    )


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


def generate_oven_water_tank(appliance: Appliance) -> list[HCSensorEntityDescription]:
    """Get the per-cavity Water tank descriptions."""
    descriptions = []
    for group, group_name in oven_status_cavities(appliance).items():
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
    for group, group_name in oven_status_cavities(appliance).items():
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


SENSOR_ENTITY_DESCRIPTIONS: _EntityDescriptionsDefinitionsType = {
    "sensor": [
        # BSH.Common
        generate_door_sensor,
        generate_last_program_consumption,
        # Gaggenau BO470112 and BS474112 (upstream #513)
        HCSensorEntityDescription(
            key="sensor_stopwatch_time",
            entity=StatusKey.BSH_COMMON_STOP_WATCH_TIME,
            device_class=SensorDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.SECONDS,
        ),
        HCSensorEntityDescription(
            key="sensor_stopwatch_state",
            entity=StatusKey.BSH_COMMON_STOP_WATCH_STATE,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        HCSensorEntityDescription(
            key="sensor_remaining_program_time",
            entity=OptionKey.BSH_COMMON_REMAINING_PROGRAM_TIME,
            device_class=SensorDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            suggested_unit_of_measurement=UnitOfTime.HOURS,
            extra_attributes=[
                {
                    "name": "Is Estimated",
                    "entity": OptionKey.BSH_COMMON_REMAINING_PROGRAM_TIME_IS_ESTIMATED,
                }
            ],
            clear_on_expected_offline=True,
            program_sensor=True,
        ),
        HCSensorEntityDescription(
            key="sensor_elapsed_program_time",
            entity=OptionKey.BSH_COMMON_ELAPSED_PROGRAM_TIME,
            device_class=SensorDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            suggested_unit_of_measurement=UnitOfTime.HOURS,
            clear_on_expected_offline=True,
            program_sensor=True,
            available_while_program_active=True,
        ),
        HCSensorEntityDescription(
            key="sensor_program_progress",
            entity=OptionKey.BSH_COMMON_PROGRAM_PROGRESS,
            native_unit_of_measurement=PERCENTAGE,
            clear_on_expected_offline=True,
            program_sensor=True,
            available_with_remaining_time=True,
        ),
        HCSensorEntityDescription(
            key="sensor_water_forecast",
            entity=OptionKey.BSH_COMMON_WATER_FORECAST,
            native_unit_of_measurement=PERCENTAGE,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        HCSensorEntityDescription(
            key="sensor_energy_forecast",
            entity=OptionKey.BSH_COMMON_ENERGY_FORECAST,
            native_unit_of_measurement=PERCENTAGE,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        HCSensorEntityDescription(
            key="sensor_operation_state",
            entity=StatusKey.BSH_COMMON_OPERATION_STATE,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        HCSensorEntityDescription(
            key="sensor_start_in",
            entity=OptionKey.BSH_COMMON_START_IN_RELATIVE,
            device_class=SensorDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            suggested_unit_of_measurement=UnitOfTime.HOURS,
        ),
        HCSensorEntityDescription(
            key="sensor_finish_in",
            entity=OptionKey.BSH_COMMON_FINISH_IN_RELATIVE,
            device_class=SensorDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            suggested_unit_of_measurement=UnitOfTime.HOURS,
        ),
        HCSensorEntityDescription(
            key="sensor_count_started",
            entity=StatusKey.BSH_COMMON_PROGRAM_ALL_COUNT_STARTED,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            state_class=SensorStateClass.TOTAL_INCREASING,
            extra_attributes=[
                {
                    "name": "Last Start",
                    "entity": StatusKey.BSH_COMMON_PROGRAM_SESSION_SUMMARY_LATEST,
                    "value_fn": lambda entity: (
                        entity.value["start"] if entity.value is not None else None
                    ),
                },
                {
                    "name": "Last End",
                    "entity": StatusKey.BSH_COMMON_PROGRAM_SESSION_SUMMARY_LATEST,
                    "value_fn": lambda entity: (
                        entity.value["end"] if entity.value is not None else None
                    ),
                },
            ],
        ),
        HCSensorEntityDescription(
            key="sensor_count_completed",
            entity=StatusKey.BSH_COMMON_PROGRAM_ALL_COUNT_COMPLETED,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            state_class=SensorStateClass.TOTAL_INCREASING,
        ),
        HCSensorEntityDescription(
            key="sensor_energy_consumed",
            entity=StatusKey.BSH_COMMON_PROGRAM_ALL_ENERGY_CONSUMED,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
            suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        ),
        HCSensorEntityDescription(
            key="sensor_water_consumed",
            entity=StatusKey.BSH_COMMON_PROGRAM_ALL_WATER_CONSUMED,
            device_class=SensorDeviceClass.WATER,
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfVolume.LITERS,
            # Reported in mL, which the water device class doesn't take
            value_fn=lambda value: value / 1000 if isinstance(value, int | float) else None,
        ),
        HCSensorEntityDescription(
            key="sensor_end_trigger",
            entity=StatusKey.BSH_COMMON_PROGRAM_RUN_DETAIL_END_TRIGGER,
            device_class=SensorDeviceClass.ENUM,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        HCSensorEntityDescription(
            key="sensor_flex_start",
            entity=StatusKey.BSH_COMMON_FLEX_START,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        HCSensorEntityDescription(
            key="sensor_estimated_remaining_program_time",
            entity=OptionKey.BSH_COMMON_ESTIMATED_TOTAL_PROGRAM_TIME,
            device_class=SensorDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            suggested_unit_of_measurement=UnitOfTime.HOURS,
            clear_on_expected_offline=True,
            program_sensor=True,
            available_with_remaining_time=True,
        ),
        # Coffee machines
        HCSensorEntityDescription(
            key="sensor_countdown_calc_n_clean",
            entity=StatusKey.CONSUMER_PRODUCTS_COFFEE_MAKER_BEVERAGE_COUNTDOWN_CALC_N_CLEAN,
            entity_registry_enabled_default=False,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        HCSensorEntityDescription(
            key="sensor_countdown_cleaning",
            entity=StatusKey.CONSUMER_PRODUCTS_COFFEE_MAKER_BEVERAGE_COUNTDOWN_CLEANING,
            entity_registry_enabled_default=False,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        HCSensorEntityDescription(
            key="sensor_countdown_descaling",
            entity=StatusKey.CONSUMER_PRODUCTS_COFFEE_MAKER_BEVERAGE_COUNTDOWN_DESCALING,
            entity_registry_enabled_default=False,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        HCSensorEntityDescription(
            key="sensor_countdown_water_filter",
            entity=StatusKey.CONSUMER_PRODUCTS_COFFEE_MAKER_BEVERAGE_COUNTDOWN_WATERFILTER,
            entity_registry_enabled_default=False,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        HCSensorEntityDescription(
            key="sensor_count_ristretto_espresso",
            entity=StatusKey.CONSUMER_PRODUCTS_COFFEE_MAKER_BEVERAGE_COUNTER_RISTRETTO_ESPRESSO,
            entity_registry_enabled_default=False,
            state_class=SensorStateClass.TOTAL_INCREASING,
        ),
        HCSensorEntityDescription(
            key="sensor_count_coffee",
            entity=StatusKey.CONSUMER_PRODUCTS_COFFEE_MAKER_BEVERAGE_COUNTER_COFFEE,
            entity_registry_enabled_default=False,
            state_class=SensorStateClass.TOTAL_INCREASING,
        ),
        HCSensorEntityDescription(
            key="sensor_count_coffee_milk",
            entity=StatusKey.CONSUMER_PRODUCTS_COFFEE_MAKER_BEVERAGE_COUNTER_COFFEE_AND_MILK,
            entity_registry_enabled_default=False,
            state_class=SensorStateClass.TOTAL_INCREASING,
        ),
        HCSensorEntityDescription(
            key="sensor_count_frothy_milk",
            entity=StatusKey.CONSUMER_PRODUCTS_COFFEE_MAKER_BEVERAGE_COUNTER_FROTHY_MILK,
            entity_registry_enabled_default=False,
            state_class=SensorStateClass.TOTAL_INCREASING,
        ),
        HCSensorEntityDescription(
            key="sensor_count_hot_milk",
            entity=StatusKey.CONSUMER_PRODUCTS_COFFEE_MAKER_BEVERAGE_COUNTER_HOT_MILK,
            entity_registry_enabled_default=False,
            state_class=SensorStateClass.TOTAL_INCREASING,
        ),
        HCSensorEntityDescription(
            key="sensor_count_hot_water",
            entity=StatusKey.CONSUMER_PRODUCTS_COFFEE_MAKER_BEVERAGE_COUNTER_HOT_WATER,
            entity_registry_enabled_default=False,
            state_class=SensorStateClass.TOTAL_INCREASING,
        ),
        HCSensorEntityDescription(
            key="sensor_count_hot_water_cups",
            entity=StatusKey.CONSUMER_PRODUCTS_COFFEE_MAKER_BEVERAGE_COUNTER_HOT_WATER_CUPS,
            entity_registry_enabled_default=False,
            state_class=SensorStateClass.TOTAL_INCREASING,
        ),
        HCSensorEntityDescription(
            key="sensor_count_powder_coffee",
            entity=StatusKey.CONSUMER_PRODUCTS_COFFEE_MAKER_BEVERAGE_COUNTER_POWDER_COFFEE,
            entity_registry_enabled_default=False,
            state_class=SensorStateClass.TOTAL_INCREASING,
        ),
        HCSensorEntityDescription(
            key="sensor_coffeemaker_process_phase",
            entity=StatusKey.CONSUMER_PRODUCTS_COFFEE_MAKER_PROCESS_PHASE,
            entity_registry_enabled_default=False,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        # Cooking
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
        # Dishwashers
        HCSensorEntityDescription(
            key="sensor_program_phase",
            entity=StatusKey.DISHCARE_DISHWASHER_PROGRAM_PHASE,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
            program_sensor=True,
        ),
        HCSensorEntityDescription(
            key="sensor_machine_care_reminder",
            entity=StatusKey.DISHCARE_DISHWASHER_MACHINE_CARE_REMINDER_REMAINING_PROGRAM_RUNS,
            entity_category=EntityCategory.DIAGNOSTIC,
            # The unit's text is in the translations (unit_of_measurement).
            state_class=SensorStateClass.MEASUREMENT,
        ),
        # Laundry
        HCSensorEntityDescription(
            key="sensor_laundry_reload",
            entity=StatusKey.LAUNDRY_CARE_COMMON_LAUNDRY_RELOAD,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        HCSensorEntityDescription(
            key="sensor_laundry_process_phase",
            entity=OptionKey.LAUNDRY_CARE_COMMON_PROCESS_PHASE,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        HCSensorEntityDescription(
            key="sensor_dryer_process_phase",
            entity=OptionKey.LAUNDRY_CARE_DRYER_PROCESS_PHASE,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
        ),
        HCSensorEntityDescription(
            key="sensor_laundry_load_recommendation",
            entity=OptionKey.LAUNDRY_CARE_COMMON_LOAD_RECOMMENDATION,
            device_class=SensorDeviceClass.WEIGHT,
            native_unit_of_measurement=UnitOfMass.GRAMS,
            suggested_unit_of_measurement=UnitOfMass.KILOGRAMS,
        ),
        HCSensorEntityDescription(
            key="sensor_laundry_load",
            entity=StatusKey.LAUNDRY_CARE_WASHER_PROCESSING_DATA_LAUNDRY_LOAD,
            device_class=SensorDeviceClass.WEIGHT,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfMass.GRAMS,
            suggested_unit_of_measurement=UnitOfMass.KILOGRAMS,
            # 0 means the load hasn't been measured yet, and some washers send 65535 (0xFFFF)
            # when a program finishes (fork issue #254)
            value_fn=lambda value: None if value in (0, 0xFFFF) else value,
        ),
        HCSensorEntityDescription(
            key="sensor_laundry_detergent_consumed",
            entity=StatusKey.LAUNDRY_CARE_WASHER_DETERGENT_ALL_CONSUMED,
            device_class=SensorDeviceClass.VOLUME,
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfVolume.MILLILITERS,
        ),
        HCSensorEntityDescription(
            key="sensor_laundry_softener_consumed",
            entity=StatusKey.LAUNDRY_CARE_WASHER_SOFTENER_ALL_CONSUMED,
            device_class=SensorDeviceClass.VOLUME,
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfVolume.MILLILITERS,
        ),
        HCSensorEntityDescription(
            key="sensor_laundry_status_idos1_fill_level",
            entity=StatusKey.LAUNDRY_CARE_WASHER_I_DOS_1_FILL_LEVEL,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
            entity_registry_enabled_default=False,
        ),
        HCSensorEntityDescription(
            key="sensor_laundry_status_idos2_fill_level",
            entity=StatusKey.LAUNDRY_CARE_WASHER_I_DOS_2_FILL_LEVEL,
            device_class=SensorDeviceClass.ENUM,
            has_state_translation=True,
            entity_registry_enabled_default=False,
        ),
        # Refrigeration
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
    "event_sensor": [
        # Coffee machines
        HCSensorEntityDescription(
            key="sensor_water_tank",
            entities=[
                EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_WATER_TANK_EMPTY,
                EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_WATER_TANK_NEARLY_EMPTY,
                EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_WATER_TANK_NOT_INSERTED,
            ],
            device_class=SensorDeviceClass.ENUM,
            options=["empty", "nearly_empty", "not_inserted", "full"],
        ),
        HCSensorEntityDescription(
            key="sensor_drip_tray",
            entities=[
                EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_DRIP_TRAY_FULL,
                EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_DRIP_TRAY_NOT_INSERTED,
            ],
            device_class=SensorDeviceClass.ENUM,
            options=["full", "not_inserted", "ok"],
        ),
        HCSensorEntityDescription(
            key="sensor_coffee_descaling",
            entities=[
                EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_DEVICE_DESCALING_BLOCKAGE,
                EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_DEVICE_DESCALING_OVERDUE,
                EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_DEVICE_SHOULD_BE_DESCALED,
            ],
            device_class=SensorDeviceClass.ENUM,
            options=["blocked", "overdue", "due", "ok"],
        ),
        HCSensorEntityDescription(
            key="sensor_coffee_care_program_step",
            entities=[
                EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_EMPTY_DRIP_TRAY,
                EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_EMPTY_DRIP_TRAY_REMOVE_CONTAINER,
                EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_THROW_CLEANING_DISC_IN_THE_DRAWER,
                EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_FILL_DESCALER,
                EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_EMPTY_MILK_TANK,
                EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_PLACE_EMPTY_GLASS_UNDER_OUTLET,
                EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_PLACE_CONTAINER_UNDER_OUTLET,
                EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_CLEAN_MILK_TANK,
                EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_CLEAN_FILL_WATER_TANK,
                EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_REMOVE_CONTAINER_UNDER_OUTLET,
                EventKey.CONSUMER_PRODUCTS_COFFEE_MAKER_SERVICE_PROGRAM_FINISHED,
            ],
            device_class=SensorDeviceClass.ENUM,
            options=[
                "empty_drip_tray",
                "empty_drip_tray_remove_container",
                "insert_cleaning_tablet",
                "fill_descaler",
                "empty_milk_container",
                "place_empty_glass",
                "place_container",
                "clean_milk_container",
                "rinse_and_fill_water_tank",
                "remove_container",
                "finished",
                "none",
            ],
        ),
        # Cooking
        generate_oven_water_tank,
        # Dishwashers
        HCSensorEntityDescription(
            key="sensor_rinse_aid",
            entities=[
                EventKey.DISHCARE_DISHWASHER_RINSE_AID_LACK,
                EventKey.DISHCARE_DISHWASHER_RINSE_AID_NEARLY_EMPTY,
            ],
            device_class=SensorDeviceClass.ENUM,
            options=["empty", "nearly_empty", "full"],
        ),
        HCSensorEntityDescription(
            key="sensor_salt",
            entities=[
                EventKey.DISHCARE_DISHWASHER_SALT_LACK,
                EventKey.DISHCARE_DISHWASHER_SALT_NEARLY_EMPTY,
            ],
            device_class=SensorDeviceClass.ENUM,
            options=["empty", "nearly_empty", "full"],
        ),
    ],
    "active_program": [generate_active_program],
    "wifi": [generate_wifi],
    "ipv4": [generate_ipv4],
    "ipv6": [generate_ipv6],
}


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    config_entry: HCConfigEntry,
    async_add_entites: AddEntitiesCallback,
) -> None:
    """Set up sensor platform."""
    entities = create_entities(
        {
            "sensor": HCSensor,
            "event_sensor": HCEventSensor,
            "active_program": HCActiveProgram,
            "wifi": HCWiFI,
            "ipv4": HCIPv4Address,
            "ipv6": HCIPv6Address,
        },
        config_entry.runtime_data,
    )
    problem_descriptions = [
        cast("HCBinarySensorEntityDescription", description)
        for description in config_entry.runtime_data.available_entity_descriptions.get(
            "binary_sensor", []
        )
        if description.device_class == BinarySensorDeviceClass.PROBLEM
        and cast("HCBinarySensorEntityDescription", description).in_problem_sensor
    ]
    if problem_descriptions:
        entities.add(HCProblemSensor(problem_descriptions, config_entry.runtime_data))
    async_add_entites(entities)


class HCSensor(HCEntity, SensorEntity):
    """Sensor Entity."""

    entity_description: HCSensorEntityDescription

    def __init__(
        self,
        entity_description: HCSensorEntityDescription,
        runtime_data: HCData,
    ) -> None:
        super().__init__(entity_description, runtime_data)

        if self._entity is not None and self._entity.enum:
            if self.entity_description.has_state_translation:
                self._attr_options = [str(value).lower() for value in self._entity.enum.values()]
            else:
                self._attr_options = [str(value) for value in self._entity.enum.values()]

        # Availability also depends on these, which the sensor's own entity doesn't
        # report: without listening to them, nothing would update the sensor once its
        # program ends. Same pattern as fan.py's _HOOD_FAN_STATE_ENTITIES.
        triggers: list[str] = []
        if entity_description.program_sensor:
            triggers.append(_OPERATION_STATE_ENTITY)
        if (
            entity_description.available_while_program_active
            or entity_description.available_with_remaining_time
        ):
            triggers.append(_ACTIVE_PROGRAM_ENTITY)
        if entity_description.available_with_remaining_time:
            triggers.append(_REMAINING_PROGRAM_TIME_ENTITY)
        for name in triggers:
            trigger_entity = runtime_data.appliance.entities.get(name)
            if trigger_entity is not None and trigger_entity not in self._entities:
                self._entities.append(trigger_entity)

    @property
    def native_unit_of_measurement(self) -> str | None:
        return self._temperature_unit or super().native_unit_of_measurement

    @property
    def native_value(self) -> int | float | str | None:
        if self.entity_description.clear_on_expected_offline and (
            self._runtime_data.coordinator.expected_offline
        ):
            return None
        if self._entity is None or self._entity.value is None:
            return None
        if self._entity.enum and self.entity_description.has_state_translation:
            return str(self._entity.value).lower()
        if (value_fn := self.entity_description.value_fn) is not None:
            value = value_fn(self._entity.value)
        else:
            value = cast("int | float | str", self._entity.value)
        return value

    @property
    def available(self) -> bool:
        if self.entity_description.program_sensor and not _program_running(
            self._runtime_data.appliance
        ):
            return False
        if (
            self._runtime_data.appliance.active_program is not None
            and self._entity is not None
            and self._entity.value is not None
            and (
                self.entity_description.available_while_program_active
                or (
                    self.entity_description.available_with_remaining_time
                    and self._has_remaining_time()
                )
            )
        ):
            return self._runtime_data.appliance.connected
        return super().available

    def _has_remaining_time(self) -> bool:
        remaining_time = self._runtime_data.appliance.entities.get(_REMAINING_PROGRAM_TIME_ENTITY)
        return (
            remaining_time is not None
            and remaining_time.value is not None
            and entity_is_available(remaining_time, (Access.READ, Access.READ_WRITE))
        )


class HCEventSensor(HCEntity, SensorEntity):
    """Event Sensor Entity."""

    entity_description: HCSensorEntityDescription

    @property
    def native_value(self) -> str:
        options = self.entity_description.options or []
        for entity, value in zip(self._entities, options, strict=False):
            if isinstance(entity, Program):
                continue
            if (entity.enum is not None and entity.value in {"Present", "Confirmed"}) or (
                entity.enum is None and bool(entity.value)
            ):
                return value
        return options[-1]

    @property
    def available(self) -> bool:
        return (
            self._runtime_data.appliance.connected
            or self._runtime_data.coordinator.expected_offline
        )


PROBLEM_SENSOR_KEY = "sensor_problem"
PROBLEM_OK = "ok"


def problem_state(description: HCBinarySensorEntityDescription) -> str:
    """Get the Problem sensor's state for a problem: its binary sensor's key, unprefixed."""
    return (description.translation_key or description.key).removeprefix("binary_sensor_")


class HCProblemSensor(HCEntity, SensorEntity):
    """
    Which problem is stopping the appliance from working, or "ok".

    Alarms and reminders (in_problem_sensor=False) have their own binary sensors instead. The
    per-problem binary sensors counted here are disabled by default, so this is the one to
    watch; enable one to see or automate on that problem alone, also while another one is
    shown here.
    """

    entity_description: HCSensorEntityDescription

    def __init__(
        self, problem_descriptions: list[HCBinarySensorEntityDescription], runtime_data: HCData
    ) -> None:
        super().__init__(
            HCSensorEntityDescription(
                key=PROBLEM_SENSOR_KEY,
                entities=[
                    description.entity for description in problem_descriptions if description.entity
                ],
                device_class=SensorDeviceClass.ENUM,
            ),
            runtime_data,
        )
        self._problems = [
            (problem_state(description), description, runtime_data.appliance.entities[entity])
            for description in problem_descriptions
            if (entity := description.entity)
        ]
        self._attr_options = list(dict.fromkeys([PROBLEM_OK] + [p[0] for p in self._problems]))

    @property
    def native_value(self) -> str | None:
        states = [
            (state, binary_is_on(description, entity))
            for state, description, entity in self._problems
        ]
        for state, is_on in states:
            if is_on:
                return state
        if all(is_on is None for _, is_on in states):
            # None of them reported yet.
            return None
        # A problem the appliance hasn't reported isn't active.
        return PROBLEM_OK


class HCActiveProgram(HCSensor):
    """Active Program Sensor Entity."""

    def __init__(
        self,
        entity_description: HCSensorEntityDescription,
        runtime_data: HCData,
    ) -> None:
        super().__init__(entity_description, runtime_data)
        self._attr_options = list((entity_description.mapping or {}).values())

    @property
    def native_value(self) -> str | None:
        if self.entity_description.clear_on_expected_offline and (
            self._runtime_data.coordinator.expected_offline
        ):
            return None
        if self._runtime_data.appliance.active_program:
            mapping = self.entity_description.mapping or {}
            if self._runtime_data.appliance.active_program.name in mapping:
                return mapping[self._runtime_data.appliance.active_program.name]
            return self._runtime_data.appliance.active_program.name
        return None


class HCWiFI(HCEntity, SensorEntity):
    """WiFi signal Sensor Entity, polled since the appliance never pushes it."""

    entity_description: HCSensorEntityDescription

    @property
    def should_poll(self) -> bool:
        # HCEntity inherits from CoordinatorEntity, whose should_poll is a hardcoded
        # False and takes priority over Entity's (which reads _attr_should_poll) in
        # the MRO - setting _attr_should_poll here alone is silently ignored. This
        # explicit override is required for the SCAN_INTERVAL polling below to
        # actually run at all.
        return True

    def __init__(
        self,
        entity_description: HCSensorEntityDescription,
        runtime_data: HCData,
    ) -> None:
        super().__init__(entity_description, runtime_data)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Without this, the platform's SCAN_INTERVAL timer wouldn't fire the
        # first poll until a full interval after setup/reload - get a value
        # immediately instead of sitting at unknown for up to an hour. Scheduled
        # rather than awaited: the /ni/info request has no timeout and would
        # otherwise hold up the whole sensor platform setup.
        self.async_schedule_update_ha_state(force_refresh=True)

    @property
    def icon(self) -> str:
        value = self.native_value
        if not isinstance(value, int | float):
            return "mdi:wifi-strength-outline"
        magnitude = abs(value)
        for threshold, icon in _WIFI_STRENGTH_ICONS:
            if magnitude < threshold:
                return icon
        return "mdi:wifi-strength-1-alert"

    async def async_update(self) -> None:
        network_info = await self._runtime_data.coordinator.async_get_network_info()
        if network_info and isinstance(network_info, list) and "rssi" in network_info[0]:
            self._attr_native_value = network_info[0]["rssi"]
        else:
            _LOGGER.debug("WiFi update failed: unexpected response format: %s", network_info)


class HCIPAddress(HCEntity, SensorEntity):
    """
    Base for the IPv4/IPv6 address sensors.

    Polled the same way as HCWiFI (see its docstring/should_poll override),
    sharing the same /ni/info data through the coordinator's cache rather than
    each issuing its own request - see NETWORK_INFO_COALESCE_WINDOW in
    coordinator.py.
    """

    entity_description: HCSensorEntityDescription
    # Set by the two concrete subclasses below - "ipV4" or "ipV6", matching
    # the key /ni/info nests each interface's address block under.
    _interface_key: ClassVar[str]

    @property
    def should_poll(self) -> bool:
        # See HCWiFI.should_poll for why this override is required.
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Without this, the platform's SCAN_INTERVAL timer wouldn't fire the
        # first poll until a full interval after setup/reload - get a value
        # immediately instead of sitting at unknown for up to an hour. Scheduled
        # rather than awaited: the /ni/info request has no timeout and would
        # otherwise hold up the whole sensor platform setup.
        self.async_schedule_update_ha_state(force_refresh=True)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # HCEntity's own extra_state_attributes builds off entity_description.
        # extra_attributes (a real BSH entity's value) - these sensors have no
        # backing BSH entity at all, so that machinery doesn't apply here.
        return self._address_attributes

    def __init__(
        self,
        entity_description: HCSensorEntityDescription,
        runtime_data: HCData,
    ) -> None:
        super().__init__(entity_description, runtime_data)
        self._address_attributes: dict[str, Any] = {}

    async def async_update(self) -> None:
        network_info = await self._runtime_data.coordinator.async_get_network_info()
        if not network_info or not isinstance(network_info, list):
            _LOGGER.debug(
                "%s update failed: unexpected response format: %s",
                self.entity_description.key,
                network_info,
            )
            return
        address_info = network_info[0].get(self._interface_key)
        if not isinstance(address_info, dict):
            # Normal, not an error: an appliance with only an IPv4 or only an
            # IPv6 address simply won't have the other key in its /ni/info
            # response at all.
            self._attr_native_value = None
            self._address_attributes = {}
            return
        self._attr_native_value = address_info.get("ipAddress")
        self._address_attributes = {
            "prefix_size": address_info.get("prefixSize"),
            "gateway": address_info.get("gateway"),
            "dns_server": address_info.get("dnsServer"),
        }


class HCIPv4Address(HCIPAddress):
    """IPv4 address Sensor Entity."""

    _interface_key = "ipV4"


class HCIPv6Address(HCIPAddress):
    """IPv6 address Sensor Entity."""

    _interface_key = "ipV6"
