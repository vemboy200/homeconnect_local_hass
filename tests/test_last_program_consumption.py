"""Tests for the energy and water consumption of the last program."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

from custom_components import homeconnect_ws
from custom_components.homeconnect_ws import coordinator, entity_descriptions
from custom_components.homeconnect_ws.sensor import (
    ENERGY_CONSUMED_LAST,
    PROGRAM_SESSION_SUMMARY,
    WATER_CONSUMED_LAST,
    generate_last_program_consumption,
)
from home_disconnect import Access
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, UnitOfEnergy, UnitOfVolume
from homeassistant.helpers import entity_registry as er

from . import appliance_class, make_appliance, setup_config_entry, update_entity
from .const import DEVICE_DESCRIPTION, ENTITY_DESCRIPTIONS, MOCK_CONFIG_DATA

if TYPE_CHECKING:
    import pytest
    from homeassistant.core import HomeAssistant

    from . import MockApplianceFactory

# UIDs as reported by a Bosch WGH24400IT washer
ENERGY_UID = 628
WATER_UID = 623
SUMMARY_UID = 625

ENERGY_STATUS = {
    "uid": ENERGY_UID,
    "name": ENERGY_CONSUMED_LAST,
    "available": True,
    "access": Access.READ,
    "contentType": "energy",
    "protocolType": "Float",
}
WATER_STATUS = {
    "uid": WATER_UID,
    "name": WATER_CONSUMED_LAST,
    "available": True,
    "access": Access.READ,
    "contentType": "liquidVolume",
    "protocolType": "Integer",
}
SUMMARY_STATUS = {
    "uid": SUMMARY_UID,
    "name": PROGRAM_SESSION_SUMMARY,
    "available": True,
    "access": Access.READ,
    "contentType": "programSessionSummary",
    "protocolType": "Object",
}


def session_summary(energy: float, water: int) -> dict[str, Any]:
    """Build a Program Session Summary like the one the washer reports."""
    return {
        "start": "2026-10-11T07:44:30.927Z",
        "end": "2026-10-11T09:08:31.853Z",
        "counter": 19,
        "sequence": [
            {
                "details": [
                    {"uid": 616, "value": 18},
                    {"uid": ENERGY_UID, "value": energy},
                    {"uid": WATER_UID, "value": water},
                ]
            }
        ],
    }


async def test_without_last_program_statuses(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """Appliances without Program.Last statuses get no sensors."""
    appliance = await mock_homeconnect_appliance(description={"status": [SUMMARY_STATUS]})
    assert generate_last_program_consumption(appliance) == []


async def test_follows_the_status_without_a_summary(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """Without a Program Session Summary, the sensors follow the status itself."""
    appliance = await mock_homeconnect_appliance(
        description={"status": [ENERGY_STATUS, WATER_STATUS]}
    )
    energy, water = generate_last_program_consumption(appliance)

    assert energy.key == "sensor_energy_consumed_last"
    assert energy.entity == ENERGY_CONSUMED_LAST
    assert energy.entities is None
    assert energy.native_unit_of_measurement == UnitOfEnergy.WATT_HOUR
    assert water.key == "sensor_water_consumed_last"
    assert water.entity == WATER_CONSUMED_LAST
    assert water.native_unit_of_measurement == UnitOfVolume.LITERS

    assert energy.value_fn(None) is None
    await update_entity(appliance.entities[ENERGY_CONSUMED_LAST], {"value": 493.0})
    await update_entity(appliance.entities[WATER_CONSUMED_LAST], {"value": 40000})
    assert energy.value_fn(None) == 493.0
    # Water is reported in mL
    assert water.value_fn(None) == 40.0


async def test_falls_back_to_the_session_summary(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """Empty Program.Last statuses fall back to the latest Program Session Summary."""
    appliance = await mock_homeconnect_appliance(
        description={"status": [ENERGY_STATUS, WATER_STATUS, SUMMARY_STATUS]}
    )
    energy, water = generate_last_program_consumption(appliance)

    assert energy.entity == PROGRAM_SESSION_SUMMARY
    assert energy.entities == [ENERGY_CONSUMED_LAST]
    assert water.entity == PROGRAM_SESSION_SUMMARY
    assert water.entities == [WATER_CONSUMED_LAST]

    # After reconnecting the statuses stay empty, the summary still has them
    await update_entity(
        appliance.entities[PROGRAM_SESSION_SUMMARY], {"value": session_summary(493.0, 40000)}
    )
    assert appliance.entities[ENERGY_CONSUMED_LAST].value is None
    assert energy.value_fn(None) == 493.0
    assert water.value_fn(None) == 40.0

    # Once the appliance reports the status, it wins over the summary
    await update_entity(appliance.entities[ENERGY_CONSUMED_LAST], {"value": 510.0})
    assert energy.value_fn(None) == 510.0


async def test_sensors_in_home_assistant(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After reconnecting, the sensors show the values of the session summary."""
    description = deepcopy(DEVICE_DESCRIPTION)
    description["status"] = [
        *description.get("status", []),
        ENERGY_STATUS,
        WATER_STATUS,
        SUMMARY_STATUS,
    ]
    appliance = make_appliance(description)
    monkeypatch.setattr(coordinator, "Appliance", appliance_class(appliance))
    descriptions = {key: [] for key in ENTITY_DESCRIPTIONS}
    descriptions["sensor"] = generate_last_program_consumption(appliance)
    for module in (entity_descriptions, homeconnect_ws):
        monkeypatch.setattr(module, "get_available_entities", Mock(return_value=descriptions))
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await update_entity(
        appliance.entities[PROGRAM_SESSION_SUMMARY], {"value": session_summary(493.0, 40000)}
    )
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    states = {}
    for entry in registry.entities.values():
        if entry.unique_id.endswith(
            ("-sensor_energy_consumed_last", "-sensor_water_consumed_last")
        ):
            states[entry.unique_id.rsplit("-", 1)[1]] = hass.states.get(entry.entity_id)
    energy = states["sensor_energy_consumed_last"]
    water = states["sensor_water_consumed_last"]
    assert float(energy.state) == 0.493
    assert energy.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfEnergy.KILO_WATT_HOUR
    assert float(water.state) == 40.0
    assert water.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfVolume.LITERS
