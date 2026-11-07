"""Tests for number entity."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_components.homeconnect_ws import HCData, coordinator
from custom_components.homeconnect_ws.const import DOMAIN
from custom_components.homeconnect_ws.entity_descriptions.descriptions_definitions import (
    HCNumberEntityDescription,
)
from custom_components.homeconnect_ws.number import HCNumber
from home_disconnect.entities import Access
from home_disconnect.messages import Action, Message
from homeassistant.components.number import (
    ATTR_MAX,
    ATTR_MIN,
    ATTR_STEP,
    ATTR_VALUE,
    SERVICE_SET_VALUE,
    NumberDeviceClass,
)
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    CONF_DESCRIPTION,
    Platform,
    UnitOfTemperature,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from . import (
    appliance_class,
    make_appliance,
    setup_config_entry,
    setup_integration,
    update_entity,
)
from .const import MOCK_APPLIANCE_INFO, MOCK_CONFIG_DATA

if TYPE_CHECKING:
    from home_disconnect import Appliance
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import entity_registry as er


async def test_setup(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_entity_description: None,
) -> None:
    """Test setting up entity."""
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    state = hass.states.get("number.fake_brand_homeappliance_number")
    assert state
    assert state.name == "Fake_brand HomeAppliance Number"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Fake_brand HomeAppliance Number"
    assert state.attributes[ATTR_MIN] == 0
    assert state.attributes[ATTR_MAX] == 20
    assert state.attributes[ATTR_STEP] == 2


async def test_update(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_entity_description: None,
) -> None:
    """Test updating entity."""
    entity_id = "number.fake_brand_homeappliance_number"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await update_entity(mock_appliance.entities["Test.Number"], {"value": 0})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state
    assert state.state == "0"

    await update_entity(mock_appliance.entities["Test.Number"], {"value": 10})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "10"

    await update_entity(
        mock_appliance.entities["Test.Number"], {"min": 10, "max": 50, "stepSize": 5}
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.attributes[ATTR_MIN] == 10
    assert state.attributes[ATTR_MAX] == 50
    assert state.attributes[ATTR_STEP] == 5


async def test_set_value(
    hass: HomeAssistant,
    mock_appliance: Appliance,
    patch_entity_description: None,
) -> None:
    """Test setting a value."""
    entity_id = "number.fake_brand_homeappliance_number"
    assert await setup_config_entry(hass, MOCK_CONFIG_DATA)

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: "2"},
        blocking=True,
    )
    mock_appliance.session.request.assert_awaited_once_with(
        Message(
            resource="/ro/values",
            action=Action.POST,
            data=[{"uid": 204, "value": 2}],
        )
    )


async def test_native_value_cleared_when_expected_offline() -> None:
    """Stale program-duration values clear instead of showing a frozen number."""
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=True),
    )
    entity_description = HCNumberEntityDescription(
        key="number_duration", clear_on_expected_offline=True
    )
    entity = HCNumber(entity_description, runtime_data)

    assert entity.native_value is None


async def test_native_value_not_cleared_when_not_expected_offline() -> None:
    """The clearing only applies while actually expected_offline."""
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    appliance.entities["Test.Number"].value = 12960
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=False),
    )
    entity_description = HCNumberEntityDescription(
        key="number_duration", entity="Test.Number", clear_on_expected_offline=True
    )
    entity = HCNumber(entity_description, runtime_data)

    assert entity.native_value == 12960


def _setpoint_entity(
    appliance_unit: str | None,
) -> tuple[HCNumber, MagicMock, MagicMock, MagicMock]:
    """Make a freezer setpoint number reported in both units, kept in Fahrenheit."""
    celsius = MagicMock(
        value=-16, min=-24, max=-14, step=1, available=True, locked=False, set_value=AsyncMock()
    )
    fahrenheit = MagicMock(
        value=3, min=-11, max=7, step=1, available=True, locked=False, set_value=AsyncMock()
    )
    unit = MagicMock(value=appliance_unit)
    appliance = MagicMock()
    appliance.info = {"deviceID": "test_device_id"}
    appliance.entities = {
        "Test.Setpoint": celsius,
        "Test.SetpointFahrenheit": fahrenheit,
        "BSH.Common.Setting.TemperatureUnit": unit,
    }
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=False),
    )
    entity_description = HCNumberEntityDescription(
        key="number_setpoint_freezer_fahrenheit",
        entity="Test.SetpointFahrenheit",
        other_unit_entity="Test.Setpoint",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=NumberDeviceClass.TEMPERATURE,
    )
    return HCNumber(entity_description, runtime_data), celsius, fahrenheit, unit


async def test_temperature_follows_appliance_unit() -> None:
    """A temperature in both units reads the one the appliance is set to."""
    entity, celsius, fahrenheit, unit = _setpoint_entity("Fahrenheit")

    assert entity.native_value == 3
    assert entity.native_unit_of_measurement == UnitOfTemperature.FAHRENHEIT
    assert (entity.native_min_value, entity.native_max_value) == (-11, 7)

    unit.value = "Celsius"
    entity.async_write_ha_state = MagicMock()
    await entity.callback(unit)

    assert entity.native_value == -16
    assert entity.native_unit_of_measurement == UnitOfTemperature.CELSIUS
    assert (entity.native_min_value, entity.native_max_value) == (-24, -14)
    entity.async_write_ha_state.assert_called_once()

    await entity.async_set_native_value(-18)
    celsius.set_value.assert_awaited_once_with(-18)
    fahrenheit.set_value.assert_not_awaited()


async def test_temperature_keeps_its_unit_while_appliance_unit_unknown() -> None:
    """Until the appliance reports its unit, the entity keeps the one it was set up with."""
    entity, *_ = _setpoint_entity(None)

    assert entity.native_value == 3
    assert entity.native_unit_of_measurement == UnitOfTemperature.FAHRENHEIT


@pytest.mark.parametrize(
    ("brand", "expected_step"),
    [
        ("GAGGENAU", 5),  # Reports a step of 1, but rounds up to a multiple of 5
        ("Gaggenau", 5),
        ("BOSCH", 1),
    ],
)
async def test_oven_setpoint_step(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    entity_registry: er.EntityRegistry,
    brand: str,
    expected_step: int,
) -> None:
    """Test the oven's setpoint step depends on the brand, not only on what it reports."""
    info = {**MOCK_APPLIANCE_INFO, "type": "Oven", "brand": brand}
    description = {
        "option": [
            {
                "uid": 5120,
                "name": "Cooking.Oven.Option.SetpointTemperature",
                "available": True,
                "access": Access.READ_WRITE,
                "min": 30,
                "max": 300,
                "stepSize": 1,
            }
        ],
        "info": info,
    }
    appliance = make_appliance(description)
    monkeypatch.setattr(coordinator, "Appliance", appliance_class(appliance))
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={**MOCK_CONFIG_DATA, CONF_DESCRIPTION: description},
        unique_id="Test_Oven_ID",
    )

    with patch("custom_components.homeconnect_ws.PLATFORMS", [Platform.NUMBER]):
        await setup_integration(hass, config_entry)

    entity_id = entity_registry.async_get_entity_id(
        Platform.NUMBER, DOMAIN, f"{info['deviceID']}-number_oven_setpoint_temperature"
    )
    assert hass.states.get(entity_id).attributes[ATTR_STEP] == expected_step
