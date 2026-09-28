"""Tests for cooking entity description helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from custom_components.homeconnect_ws.entity_descriptions.cooking import generate_oven_status
from home_disconnect import Access
from homeassistant.const import UnitOfTemperature

if TYPE_CHECKING:
    from . import MockApplianceFactory


async def test_generate_oven_status_fahrenheit_cavity(
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
    descriptions = generate_oven_status(appliance)

    assert len(descriptions["sensor"]) == 2
    assert (
        descriptions["sensor"][0].entity
        == "Cooking.Oven.Status.Cavity.001.CurrentTemperatureFahrenheit"
    )
    assert descriptions["sensor"][0].native_unit_of_measurement == UnitOfTemperature.FAHRENHEIT
    assert (
        descriptions["sensor"][1].entity
        == "Cooking.Oven.Status.Cavity.001.MeatProbeTemperatureFahrenheit"
    )
    assert descriptions["sensor"][1].native_unit_of_measurement == UnitOfTemperature.FAHRENHEIT


async def test_generate_oven_status_prefers_celsius_cavity(
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
    descriptions = generate_oven_status(appliance)

    assert len(descriptions["sensor"]) == 1
    assert descriptions["sensor"][0].entity == "Cooking.Oven.Status.Cavity.001.CurrentTemperature"
    assert descriptions["sensor"][0].native_unit_of_measurement == UnitOfTemperature.CELSIUS


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
    descriptions = generate_oven_status(appliance)

    assert len(descriptions["sensor"]) == 1
    assert descriptions["sensor"][0].translation_placeholders == {"group_name": ""}


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
    descriptions = generate_oven_status(appliance)

    assert sorted(
        description.translation_placeholders["group_name"] for description in descriptions["sensor"]
    ) == [" 1", " 2"]
