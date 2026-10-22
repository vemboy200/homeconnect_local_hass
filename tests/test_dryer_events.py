"""Tests for the events of a Bosch WRB247C0IT dryer."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from custom_components.homeconnect_ws.entity_descriptions import get_available_entities
from homeassistant.components.binary_sensor import BinarySensorDeviceClass

if TYPE_CHECKING:
    from . import MockApplianceFactory


def _event(uid: int, name: str) -> dict[str, Any]:
    return {
        "uid": uid,
        "name": name,
        "contentType": "enumeration",
        "protocolType": "Integer",
        "enumeration": {"0": "Off", "1": "Present", "2": "Confirmed"},
    }


# UIDs as reported by the dryer
DRYER_DESCRIPTION = {
    "event": [
        _event(17668, "LaundryCare.Dryer.Event.DryingProcessFinished"),
        _event(17669, "LaundryCare.Dryer.Event.CoolDownPhaseRunning"),
        _event(17667, "LaundryCare.Dryer.Event.RefresherContainerEmpty"),
        _event(17671, "LaundryCare.Dryer.Event.DryerSelfCleaning.CleanLintFilter"),
        _event(17670, "LaundryCare.Dryer.Event.DryerSelfCleaning.CleanSelfCleaningModule"),
        _event(17691, "LaundryCare.Dryer.Event.EasyClean.Filter.RemindCleaning"),
        _event(17687, "LaundryCare.Dryer.Event.EvaporatorFrozen"),
    ],
}


def _binary_sensors(available: dict[str, list[Any]]) -> dict[str, Any]:
    return {description.key: description for description in available["binary_sensor"]}


@pytest.mark.parametrize(
    ("key", "entity"),
    [
        ("binary_sensor_drying_process_finished", "LaundryCare.Dryer.Event.DryingProcessFinished"),
        ("binary_sensor_cool_down_phase_running", "LaundryCare.Dryer.Event.CoolDownPhaseRunning"),
        (
            "binary_sensor_refresher_container_empty",
            "LaundryCare.Dryer.Event.RefresherContainerEmpty",
        ),
        (
            "binary_sensor_clean_lint_filter",
            "LaundryCare.Dryer.Event.DryerSelfCleaning.CleanLintFilter",
        ),
        (
            "binary_sensor_clean_self_cleaning_module",
            "LaundryCare.Dryer.Event.DryerSelfCleaning.CleanSelfCleaningModule",
        ),
        (
            "binary_sensor_easyclean_filter_reminder",
            "LaundryCare.Dryer.Event.EasyClean.Filter.RemindCleaning",
        ),
        ("binary_sensor_evaporator_frozen", "LaundryCare.Dryer.Event.EvaporatorFrozen"),
    ],
)
async def test_dryer_events(
    mock_homeconnect_appliance: MockApplianceFactory, key: str, entity: str
) -> None:
    """Each dryer event becomes a binary sensor, on while the event is present."""
    appliance = await mock_homeconnect_appliance(description=DRYER_DESCRIPTION)
    description = _binary_sensors(get_available_entities(appliance))[key]

    assert description.entity == entity
    assert description.value_on == {"Present", "Confirmed"}
    assert description.value_off == {"Off"}


async def test_dryer_reminders_stay_out_of_the_problem_sensor(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """Cleaning and refill reminders are problems of their own, the frozen evaporator is a fault."""
    appliance = await mock_homeconnect_appliance(description=DRYER_DESCRIPTION)
    descriptions = _binary_sensors(get_available_entities(appliance))

    for key in (
        "binary_sensor_refresher_container_empty",
        "binary_sensor_clean_lint_filter",
        "binary_sensor_clean_self_cleaning_module",
        "binary_sensor_easyclean_filter_reminder",
    ):
        assert descriptions[key].device_class == BinarySensorDeviceClass.PROBLEM
        assert descriptions[key].in_problem_sensor is False

    frozen = descriptions["binary_sensor_evaporator_frozen"]
    assert frozen.device_class == BinarySensorDeviceClass.PROBLEM
    assert frozen.in_problem_sensor is True
    assert frozen.entity_registry_enabled_default is False

    cool_down = descriptions["binary_sensor_cool_down_phase_running"]
    assert cool_down.device_class == BinarySensorDeviceClass.RUNNING
