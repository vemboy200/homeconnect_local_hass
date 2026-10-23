"""Tests for cooking entity description helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from custom_components.homeconnect_ws.entity_descriptions.cooking import (
    generate_oven_event,
    generate_oven_temperatures,
    generate_oven_water_tank,
)
from home_disconnect import Access
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import UnitOfTemperature

if TYPE_CHECKING:
    from . import MockApplianceFactory


async def test_generate_oven_temperatures_fahrenheit_cavity(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """US ovens expose Fahrenheit cavity temperatures on the local API."""
    description = {
        "status": [
            {
                "uid": 1,
                "name": "Cooking.Oven.Status.Cavity.001.CurrentTemperatureFahrenheit",
                "available": True,
                "access": Access.READ,
            },
            {
                "uid": 2,
                "name": "Cooking.Oven.Status.Cavity.001.MeatProbeTemperatureFahrenheit",
                "available": True,
                "access": Access.READ,
            },
        ]
    }
    appliance = await mock_homeconnect_appliance(description=description)
    descriptions = generate_oven_temperatures(appliance)

    assert len(descriptions) == 2
    assert descriptions[0].entity == "Cooking.Oven.Status.Cavity.001.CurrentTemperatureFahrenheit"
    assert descriptions[0].native_unit_of_measurement == UnitOfTemperature.FAHRENHEIT
    assert descriptions[1].entity == "Cooking.Oven.Status.Cavity.001.MeatProbeTemperatureFahrenheit"
    assert descriptions[1].native_unit_of_measurement == UnitOfTemperature.FAHRENHEIT


async def test_generate_oven_temperatures_prefers_celsius_cavity(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """Celsius cavity temperature is used when both units are present."""
    description = {
        "status": [
            {
                "uid": 1,
                "name": "Cooking.Oven.Status.Cavity.001.CurrentTemperature",
                "available": True,
                "access": Access.READ,
            },
            {
                "uid": 2,
                "name": "Cooking.Oven.Status.Cavity.001.CurrentTemperatureFahrenheit",
                "available": True,
                "access": Access.READ,
            },
        ]
    }
    appliance = await mock_homeconnect_appliance(description=description)
    descriptions = generate_oven_temperatures(appliance)

    assert len(descriptions) == 1
    assert descriptions[0].entity == "Cooking.Oven.Status.Cavity.001.CurrentTemperature"
    assert descriptions[0].native_unit_of_measurement == UnitOfTemperature.CELSIUS


def _cavity_status(uid: int, cavity: str, field: str) -> dict[str, Any]:
    return {
        "uid": uid,
        "name": f"Cooking.Oven.Status.Cavity.{cavity}.{field}",
        "available": True,
        "access": Access.READ,
    }


async def test_layout_only_cavity_adds_no_name_suffix(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """
    A cavity that only reports layout fields doesn't count as a second oven.

    A Thermador PRG486WDH range reports its non-smart 18" oven as cavity 120
    with only State/CavityType/LengthX/LengthY/Position, next to the smart 30"
    oven (cavity 340). Its entities used to be named "Current Temperature 340".
    """
    description = {
        "status": [
            _cavity_status(1, "340", "CurrentTemperatureFahrenheit"),
            _cavity_status(2, "340", "State"),
            _cavity_status(3, "340", "Position"),
            *(
                _cavity_status(10 + i, "120", field)
                for i, field in enumerate(("CavityType", "State", "LengthX", "LengthY", "Position"))
            ),
        ]
    }
    appliance = await mock_homeconnect_appliance(description=description)
    descriptions = generate_oven_temperatures(appliance)

    assert len(descriptions) == 1
    assert descriptions[0].translation_placeholders == {"group_name": ""}


async def test_two_real_cavities_keep_name_suffix(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """Two cavities that both report more than layout still get told apart."""
    description = {
        "status": [
            _cavity_status(1, "001", "CurrentTemperature"),
            _cavity_status(2, "002", "CurrentTemperature"),
        ]
    }
    appliance = await mock_homeconnect_appliance(description=description)
    descriptions = generate_oven_temperatures(appliance)

    assert sorted(
        description.translation_placeholders["group_name"] for description in descriptions
    ) == [" 1", " 2"]


async def test_generate_oven_water_tank_partial(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """A cavity with only one water tank status still gets the sensor."""
    description = {
        "status": [
            {
                "uid": 1,
                "name": "Cooking.Oven.Status.Cavity.001.WaterTankEmpty",
                "available": True,
                "access": Access.READ,
            },
        ]
    }
    appliance = await mock_homeconnect_appliance(description=description)
    descriptions = generate_oven_water_tank(appliance)

    assert len(descriptions) == 1
    assert descriptions[0].entities == ["Cooking.Oven.Status.Cavity.001.WaterTankEmpty"]
    assert descriptions[0].options == ["empty", "ok"]


def _cavity_event(uid: int, cavity: str, name: str) -> dict[str, Any]:
    return {
        "uid": uid,
        "name": f"Cooking.Oven.Event.Cavity.{cavity}.{name}",
        "contentType": "enumeration",
        "enumeration": {"0": "Off", "1": "Present", "2": "Confirmed"},
        "protocolType": "Integer",
    }


async def test_generate_oven_event_cooking_hints(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """Cooking hints and the temperature alert become binary sensors per cavity."""
    description = {
        "event": [
            _cavity_event(6131, "001", "AlarmClockElapsed"),
            _cavity_event(6343, "001", "InsertFoodNow"),
            _cavity_event(6340, "001", "TurnFoodNow"),
            _cavity_event(6118, "001", "CavityTemperatureTooHigh"),
        ]
    }
    appliance = await mock_homeconnect_appliance(description=description)
    sensors = {
        description.translation_key: description for description in generate_oven_event(appliance)
    }

    assert sorted(sensors) == [
        "binary_sensor_oven_alarm_clock_elapsed",
        "binary_sensor_oven_cavity_temperature_too_high",
        "binary_sensor_oven_insert_food_now",
        "binary_sensor_oven_turn_food_now",
    ]
    insert_food = sensors["binary_sensor_oven_insert_food_now"]
    assert insert_food.key == "binary_sensor_oven_insert_food_now_001"
    assert insert_food.entity == "Cooking.Oven.Event.Cavity.001.InsertFoodNow"
    assert insert_food.translation_placeholders == {"group_name": ""}
    assert insert_food.value_on == {"Present", "Confirmed"}
    assert insert_food.entity_registry_enabled_default
    # A problem sensor: disabled by default, it feeds the appliance's Problem sensor
    too_hot = sensors["binary_sensor_oven_cavity_temperature_too_high"]
    assert too_hot.device_class == BinarySensorDeviceClass.PROBLEM
    assert not too_hot.entity_registry_enabled_default


async def test_generate_oven_event_cooking_hints_per_cavity(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """With two cavities, each gets its own hints, told apart by number."""
    description = {
        "event": [
            _cavity_event(1, "001", "ProgramFinished"),
            _cavity_event(2, "002", "ProgramFinished"),
        ]
    }
    appliance = await mock_homeconnect_appliance(description=description)
    sensors = generate_oven_event(appliance)

    assert [sensor.key for sensor in sensors] == [
        "binary_sensor_oven_program_finished_001",
        "binary_sensor_oven_program_finished_002",
    ]
    assert [sensor.translation_placeholders["group_name"] for sensor in sensors] == [" 1", " 2"]
