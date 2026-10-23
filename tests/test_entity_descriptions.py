"""Tests for entity descriptions."""

from __future__ import annotations

import copy
import json
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from zoneinfo import ZoneInfo

import pytest
from custom_components.homeconnect_ws import HCData, entity_descriptions
from custom_components.homeconnect_ws.entity_descriptions import (
    HCBinarySensorEntityDescription,
    HCButtonEntityDescription,
    HCEntityDescription,
    HCLightEntityDescription,
    HCNumberEntityDescription,
    HCSelectEntityDescription,
    HCSensorEntityDescription,
    HCSwitchEntityDescription,
)
from custom_components.homeconnect_ws.entity_descriptions.common import (
    COMMON_ENTITY_DESCRIPTIONS,
    generate_door_binary_sensor,
    generate_power_select,
    generate_power_switch,
    generate_program,
    generate_start_button,
    generate_temperature_unit,
)
from custom_components.homeconnect_ws.entity_descriptions.cooking import (
    generate_hood_light,
    generate_meatprobe_plugged,
)
from custom_components.homeconnect_ws.entity_descriptions.refrigeration import (
    compartment_door,
    generate_internal_light,
    generate_internal_light_brightness,
)
from custom_components.homeconnect_ws.helpers import merge_dicts
from custom_components.homeconnect_ws.select import HCSelect
from custom_components.homeconnect_ws.sensor import (
    generate_active_program,
    generate_door_sensor,
)
from home_disconnect import Access, Execution
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.const import UnitOfTemperature

from . import update_entity

if TYPE_CHECKING:
    from home_disconnect import Appliance

    from . import MockApplianceFactory


def test_merge_dicts() -> None:
    """Test merge dicts."""
    dict1 = {"a": [1, 2], "b": [3, 4]}
    dict2 = {"b": [5, 6], "c": [7, 8]}
    out_dict = merge_dicts(dict1, dict2)
    assert out_dict == {"a": [1, 2], "b": [3, 4, 5, 6], "c": [7, 8]}


MOCK_ENTITY_DESCRIPTIONS = {
    "binary_sensor": [
        HCBinarySensorEntityDescription(key="binary_sensor_available", entity="Test.BinarySensor"),
        HCBinarySensorEntityDescription(
            key="binary_sensor_not_available", entity="Test.BinarySensor2"
        ),
    ],
    "event_sensor": [
        HCSensorEntityDescription(
            key="sensor_event_available",
            entities=[
                "Test.Event1",
                "Test.Event2",
            ],
        ),
        HCSensorEntityDescription(
            key="sensor_event_partial",
            entities=[
                "Test.Event3",
                "Test.Event1",
            ],
            options=["event_3", "event_1", "none"],
        ),
        HCSensorEntityDescription(
            key="sensor_event_not_available",
            entities=[
                "Test.Event3",
                "Test.Event4",
            ],
        ),
    ],
}


def test_get_available_entities(mock_appliance: Appliance, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test get_available_entities."""
    monkeypatch.setattr(
        entity_descriptions,
        "get_all_entity_description",
        Mock(return_value=MOCK_ENTITY_DESCRIPTIONS),
    )
    entities = entity_descriptions.get_available_entities(mock_appliance)
    assert entities["binary_sensor"] == [
        HCBinarySensorEntityDescription(key="binary_sensor_available", entity="Test.BinarySensor")
    ]
    assert entities["event_sensor"] == [
        HCSensorEntityDescription(
            key="sensor_event_available",
            entities=[
                "Test.Event1",
                "Test.Event2",
            ],
        ),
        # Test.Event3 is missing: keep the sensor with the event the appliance has
        HCSensorEntityDescription(
            key="sensor_event_partial",
            entities=["Test.Event1"],
            options=["event_1", "none"],
        ),
    ]


def test_get_available_entities_keeps_first_per_key(
    mock_appliance: Appliance, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test an appliance with both names behind one key gets only the first entity."""
    old_name = HCBinarySensorEntityDescription(
        key="binary_sensor_shared", entity="Test.BinarySensor"
    )
    new_name = HCBinarySensorEntityDescription(key="binary_sensor_shared", entity="Test.Event1")
    monkeypatch.setattr(
        entity_descriptions,
        "get_all_entity_description",
        Mock(return_value={"binary_sensor": [old_name, new_name]}),
    )
    entities = entity_descriptions.get_available_entities(mock_appliance)
    assert entities["binary_sensor"] == [old_name]


POWER_SWITCH = {
    "setting": [
        {
            "access": "readwrite",
            "available": True,
            "enumeration": {"0": "MainsOff", "1": "Off", "2": "On", "3": "Standby"},
            "min": 0,
            "max": 2,
            "uid": 539,
            "name": "BSH.Common.Setting.PowerState",
        },
    ]
}


def _power_descriptions(appliance: Appliance) -> dict[str, HCEntityDescription]:
    """Return the Power entity description per platform; there's only ever one."""
    descriptions = {
        "switch": generate_power_switch(appliance),
        "select": generate_power_select(appliance),
    }
    return {platform: description for platform, description in descriptions.items() if description}


async def test_power_switch(mock_homeconnect_appliance: MockApplianceFactory) -> None:
    """Power state gets one entity: a switch for two states, a select for more."""
    device_description = copy.deepcopy(POWER_SWITCH)

    # On/Off Switch
    device_description["setting"][0]["min"] = 1
    device_description["setting"][0]["max"] = 2
    appliance = await mock_homeconnect_appliance(description=device_description)
    power_descriptions = _power_descriptions(appliance)

    assert power_descriptions == {
        "switch": HCSwitchEntityDescription(
            key="switch_power_state",
            entity="BSH.Common.Setting.PowerState",
            device_class=SwitchDeviceClass.SWITCH,
            value_mapping=("On", "Off"),
            on_values=("On",),
            force_off_when_expected_offline=True,
        )
    }

    # More than two states: a select, enabled by default
    device_description["setting"][0]["min"] = 0
    device_description["setting"][0]["max"] = 4
    appliance = await mock_homeconnect_appliance(description=device_description)
    power_descriptions = _power_descriptions(appliance)

    assert set(power_descriptions) == {"select"}
    select = power_descriptions["select"]
    assert select.key == "select_power_state"
    assert select.options == ["mainsoff", "off", "on", "standby"]
    assert select.entity_registry_enabled_default
    assert select.force_option_when_expected_offline == "off"

    # On/MainsOff Switch
    device_description["setting"][0]["enumeration"] = {"0": "MainsOff", "2": "On"}
    appliance = await mock_homeconnect_appliance(description=device_description)
    power_descriptions = _power_descriptions(appliance)

    assert set(power_descriptions) == {"switch"}
    assert power_descriptions["switch"].value_mapping == ("On", "MainsOff")

    # Standby/Off Switch
    device_description["setting"][0]["enumeration"] = {"1": "Off", "3": "Standby"}
    appliance = await mock_homeconnect_appliance(description=device_description)
    power_descriptions = _power_descriptions(appliance)

    assert set(power_descriptions) == {"switch"}
    assert power_descriptions["switch"].value_mapping == ("Standby", "Off")
    assert power_descriptions["switch"].on_values == ("On", "Standby")

    # Two states that aren't an on/off pair: a select
    device_description["setting"][0]["enumeration"] = {"1": "Off", "2": "MainsOff"}
    appliance = await mock_homeconnect_appliance(description=device_description)
    power_descriptions = _power_descriptions(appliance)

    assert set(power_descriptions) == {"select"}
    assert power_descriptions["select"].force_option_when_expected_offline == "off"

    # Neither "Off" nor "MainsOff" is a valid state for this appliance at all -
    # nothing to force to, so it should fall back to None rather than an
    # invalid option.
    device_description["setting"][0]["enumeration"] = {"2": "On", "3": "Standby", "4": "Eco"}
    appliance = await mock_homeconnect_appliance(description=device_description)
    power_descriptions = _power_descriptions(appliance)

    assert set(power_descriptions) == {"select"}
    assert power_descriptions["select"].force_option_when_expected_offline is None


async def test_power_select_when_profile_says_read(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """
    A power state the profile marks "read" still gets a select, not a sensor.

    Fork issue #7's Bosch WAU28PEHSN washer has access="read" with min 0 and
    max 3 in its profile, and was turned off through its power state select.
    """
    device_description = copy.deepcopy(POWER_SWITCH)
    device_description["setting"][0]["access"] = "read"
    device_description["setting"][0]["min"] = 0
    device_description["setting"][0]["max"] = 3
    appliance = await mock_homeconnect_appliance(description=device_description)
    power_descriptions = _power_descriptions(appliance)

    assert set(power_descriptions) == {"select"}
    assert sorted(power_descriptions["select"].options) == ["mainsoff", "off", "on", "standby"]


async def test_power_switch_present_on_venting_hood(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """
    A hood with a Venting program must still get a power switch.

    Confirmed live on fork issue #26 (a second hood owner, distinct from
    #14's) - a previous fix for a 400 reproduced on select.select_option
    re-activating Venting (a write to a different resource entirely,
    /ro/activeProgram, not this switch's /ro/values PowerState write) hid
    the switch for every hood with venting capability, permanently, not
    just while actually venting - never confirmed against the switch
    itself. That cost every venting-capable hood a working, automation-
    friendly entity for a bug that wasn't shown to involve it.
    """
    device_description = POWER_SWITCH.copy()
    device_description["setting"][0]["min"] = 1
    device_description["setting"][0]["max"] = 2
    device_description["setting"][0]["enumeration"] = {
        "0": "MainsOff",
        "1": "Off",
        "2": "On",
        "3": "Standby",
    }
    device_description["program"] = [
        {
            "uid": 900,
            "name": "Cooking.Common.Program.Hood.Venting",
            "available": True,
        },
    ]
    appliance = await mock_homeconnect_appliance(description=device_description)
    assert generate_power_select(appliance) is None
    assert generate_power_switch(appliance) == HCSwitchEntityDescription(
        key="switch_power_state",
        entity="BSH.Common.Setting.PowerState",
        device_class=SwitchDeviceClass.SWITCH,
        value_mapping=("On", "Off"),
        on_values=("On",),
        force_off_when_expected_offline=True,
    )


HOOD_LIGHT = {
    "setting": [
        {
            "access": "readwrite",
            "available": True,
            "uid": 700,
            "name": "Cooking.Common.Setting.Lighting",
        },
        {
            "access": "readwrite",
            "available": True,
            "uid": 701,
            "name": "Cooking.Common.Setting.LightingBrightness",
        },
        {
            "access": "readwrite",
            "available": False,
            "uid": 702,
            "name": "Cooking.Hood.Setting.ColorTemperaturePercent",
        },
    ]
}


async def test_hood_light(mock_homeconnect_appliance: MockApplianceFactory) -> None:
    """
    A declared-but-unavailable ColorTemperaturePercent shouldn't be used.

    Confirmed live on fork issue #15 (Bosch DWK91LT60): the appliance
    declares ColorTemperaturePercent in its profile but marks it
    unavailable - checking membership alone picked that branch anyway,
    referencing an unavailable entity and making the whole light report
    Unavailable even though on/off + brightness control works fine.
    """
    appliance = await mock_homeconnect_appliance(description=HOOD_LIGHT)

    assert generate_hood_light(appliance) == HCLightEntityDescription(
        key="light_cooking_lighting",
        entity="Cooking.Common.Setting.Lighting",
        brightness_entity="Cooking.Common.Setting.LightingBrightness",
    )

    # Once the appliance actually reports it available, the color
    # temperature branch should be used.
    await update_entity(
        appliance.entities["Cooking.Hood.Setting.ColorTemperaturePercent"], {"available": True}
    )
    assert generate_hood_light(appliance) == HCLightEntityDescription(
        key="light_cooking_lighting",
        entity="Cooking.Common.Setting.Lighting",
        brightness_entity="Cooking.Common.Setting.LightingBrightness",
        color_temperature_entity="Cooking.Hood.Setting.ColorTemperaturePercent",
    )


PROGRAM = {
    "setting": [
        {
            "uid": 101,
            "name": "BSH.Common.Setting.Favorite.001.Name",
            "access": Access.READ_WRITE,
            "available": True,
            "max": 30,
            "min": 0,
            "default": "Named Favorite",
        },
        {
            "uid": 102,
            "name": "BSH.Common.Setting.Favorite.002.Name",
            "access": Access.READ_WRITE,
            "available": True,
            "max": 30,
            "min": 0,
            "default": "",
        },
    ],
    "program": [
        {
            "uid": 201,
            "name": "BSH.Common.Program.Favorite.001",
            "available": True,
        },
        {
            "uid": 202,
            "name": "BSH.Common.Program.Favorite.002",
            "available": True,
        },
        {
            "uid": 500,
            "name": "BSH.Common.Program.Program1",
        },
    ],
}


async def test_program(mock_homeconnect_appliance: MockApplianceFactory) -> None:
    """Test dynamic Program."""
    appliance = await mock_homeconnect_appliance(description=PROGRAM)
    # The names come from the values the appliance reports, not the profile's defaults.
    appliance.entities.apply([{"uid": 101, "value": "Named Favorite"}, {"uid": 102, "value": ""}])
    assert generate_program(appliance) == HCSelectEntityDescription(
        key="select_program",
        entity="BSH.Common.Root.SelectedProgram",
        has_state_translation=False,
        mapping={
            "BSH.Common.Program.Favorite.001": "Named Favorite",
            "BSH.Common.Program.Favorite.002": "favorite_002",
            "BSH.Common.Program.Program1": "bsh_common_program_program1",
        },
    )
    assert generate_active_program(appliance) == HCSensorEntityDescription(
        key="sensor_active_program",
        entity="BSH.Common.Root.ActiveProgram",
        has_state_translation=False,
        device_class=SensorDeviceClass.ENUM,
        mapping={
            "BSH.Common.Program.Favorite.001": "Named Favorite",
            "BSH.Common.Program.Favorite.002": "favorite_002",
            "BSH.Common.Program.Program1": "bsh_common_program_program1",
        },
        clear_on_expected_offline=True,
    )

    appliance = await mock_homeconnect_appliance(description={})
    assert generate_program(appliance) is None
    assert generate_active_program(appliance) is None


async def test_start_button_created_when_execution_not_yet_populated(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """
    The start button must still be created before the appliance's real execution value arrives.

    Confirmed live on fork issue #21: get_available_entities() (which calls
    this generator) runs before coordinator.async_config_entry_first_refresh()
    even attempts a connection - for laundry appliances, whose setup is
    deliberately non-blocking, that can mean no live data has arrived yet at
    all. program.execution then reads whatever the static profile export
    defaults to, which real profile exports show is frequently the
    placeholder "none", not the appliance's real execution type. Requiring a
    positive SELECT_AND_START/SELECT_ONLY match meant the button silently
    never got created for the rest of the session. Permissive-by-default
    (exclude only confirmed START_ONLY) fixes this without needing to change
    when this generator runs.
    """
    description = {
        "program": [
            {
                "uid": 500,
                "name": "Test.Program.Placeholder",
                "execution": Execution.NONE,
            },
        ],
    }
    appliance = await mock_homeconnect_appliance(description=description)

    assert generate_start_button(appliance) == HCButtonEntityDescription(
        key="button_start_program",
        entity="BSH.Common.Root.ActiveProgram",
        entities=["BSH.Common.Root.SelectedProgram"],
    )


async def test_start_button_not_created_for_start_only_programs(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """START_ONLY programs already start on selection - they don't need this button."""
    description = {
        "program": [
            {
                "uid": 500,
                "name": "Test.Program.StartOnly",
                "execution": Execution.START_ONLY,
            },
        ],
    }
    appliance = await mock_homeconnect_appliance(description=description)

    assert generate_start_button(appliance) is None


HOOD_BOOST = {
    "info": {"deviceID": "test_device_id"},
    "option": [
        {
            "access": "readwrite",
            "available": True,
            # Matches the real IntensiveStage enum from a hood's own
            # FeatureMapping (confirmed live on fork issue #17) - a 3-way
            # stage, not a boolean, which is why this is a select rather
            # than a switch.
            "enumeration": {
                "0": "IntensiveStageOff",
                "1": "IntensiveStage1",
                "2": "IntensiveStage2",
            },
            "uid": 5000,
            "name": "Cooking.Common.Option.Hood.Boost",
        },
    ],
}


async def test_hood_boost_is_a_three_stage_select(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """switch_hood_boost was replaced by select_hood_boost - a boolean can't represent 2 stages."""
    appliance = await mock_homeconnect_appliance(description=HOOD_BOOST)
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=False),
    )
    entity_description = HCSelectEntityDescription(
        key="select_hood_boost",
        entity="Cooking.Common.Option.Hood.Boost",
        has_state_translation=True,
    )
    entity = HCSelect(entity_description, runtime_data)

    assert entity.options == [
        "intensivestageoff",
        "intensivestage1",
        "intensivestage2",
    ]

    await update_entity(appliance.entities["Cooking.Common.Option.Hood.Boost"], {"value": 2})
    assert entity.current_option == "intensivestage2"


HOOD_COLOR_TEMPERATURE = {
    "info": {"deviceID": "test_device_id"},
    "setting": [
        {
            "access": "readwrite",
            "available": True,
            # Matches the real ColorTemperature enum from a hood's own
            # FeatureMapping (confirmed live on fork issue #15) - a mode
            # selector, distinct from ColorTemperaturePercent's raw value.
            "enumeration": {
                "0": "custom",
                "1": "warm",
                "2": "warmToNeutral",
                "3": "neutral",
                "4": "neutralToCold",
                "5": "cold",
            },
            "uid": 6000,
            "name": "Cooking.Hood.Setting.ColorTemperature",
        },
    ],
}


async def test_hood_color_temperature_mode_select(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """select_hood_color_temperature_mode exposes the hood's warm/neutral/cold enum."""
    appliance = await mock_homeconnect_appliance(description=HOOD_COLOR_TEMPERATURE)
    runtime_data = HCData(
        appliance=appliance,
        device_info=MagicMock(),
        available_entity_descriptions=MagicMock(),
        coordinator=MagicMock(expected_offline=False),
    )
    entity_description = HCSelectEntityDescription(
        key="select_hood_color_temperature_mode",
        entity="Cooking.Hood.Setting.ColorTemperature",
        has_state_translation=True,
    )
    entity = HCSelect(entity_description, runtime_data)

    assert entity.options == [
        "custom",
        "warm",
        "warmtoneutral",
        "neutral",
        "neutraltocold",
        "cold",
    ]

    await update_entity(appliance.entities["Cooking.Hood.Setting.ColorTemperature"], {"value": 4})
    assert entity.current_option == "neutraltocold"


INTERNAL_LIGHT = {
    "setting": [
        {
            "uid": 0x5001,
            "name": "Refrigeration.Common.Setting.Light.Internal.Power",
            "access": Access.READ_WRITE,
            "available": True,
        },
        {
            "uid": 0x5002,
            "name": "Refrigeration.Common.Setting.Light.Internal.Brightness",
            "access": Access.READ_WRITE,
            "available": True,
            "max": 100,
            "min": 0,
        },
    ]
}


async def test_internal_light(mock_homeconnect_appliance: MockApplianceFactory) -> None:
    """Test dynamic internal light."""
    # Power + Brightness
    appliance = await mock_homeconnect_appliance(description=INTERNAL_LIGHT)
    assert generate_internal_light(appliance) == HCLightEntityDescription(
        key="light_internal",
        entity="Refrigeration.Common.Setting.Light.Internal.Power",
        brightness_entity="Refrigeration.Common.Setting.Light.Internal.Brightness",
    )

    # Power only
    power_only = {"setting": [INTERNAL_LIGHT["setting"][0]]}
    appliance = await mock_homeconnect_appliance(description=power_only)
    assert generate_internal_light(appliance) == HCLightEntityDescription(
        key="light_internal",
        entity="Refrigeration.Common.Setting.Light.Internal.Power",
    )

    # Fixed power: the light can't be switched
    fixed = copy.deepcopy(INTERNAL_LIGHT)
    fixed["setting"][0]["access"] = Access.READ_STATIC
    appliance = await mock_homeconnect_appliance(description=fixed)
    assert generate_internal_light(appliance) is None
    assert generate_internal_light_brightness(appliance).entity_registry_enabled_default

    # No internal light
    appliance = await mock_homeconnect_appliance(description={})
    assert generate_internal_light(appliance) is None


async def test_internal_light_brightness(mock_homeconnect_appliance: MockApplianceFactory) -> None:
    """Test the brightness number defers to the light entity."""
    # Light entity owns brightness, so the number is opt-in
    appliance = await mock_homeconnect_appliance(description=INTERNAL_LIGHT)
    description = generate_internal_light_brightness(appliance)
    assert description.entity_registry_enabled_default is False

    # No light entity to own it, so the number is the only control
    brightness_only = {"setting": [INTERNAL_LIGHT["setting"][1]]}
    appliance = await mock_homeconnect_appliance(description=brightness_only)
    description = generate_internal_light_brightness(appliance)
    assert description.entity_registry_enabled_default is True

    # No brightness at all
    appliance = await mock_homeconnect_appliance(description={})
    assert generate_internal_light_brightness(appliance) is None


TRANSLATION_DOMAINS = {
    "active_program": "sensor",
    "binary_sensor": "binary_sensor",
    "button": "button",
    "event_sensor": "sensor",
    "fan": "fan",
    "light": "light",
    "number": "number",
    "program": "select",
    "select": "select",
    "sensor": "sensor",
    "start_button": "button",
    "delay_start": "select",
    "switch": "switch",
    "update": "update",
    "wifi": "sensor",
    "ipv4": "sensor",
    "ipv6": "sensor",
}


def test_descriptions_have_english_name() -> None:
    """Test every entity description resolves to a name in en.json."""
    translations = json.loads(
        Path("custom_components/homeconnect_ws/translations/en.json").read_text(encoding="utf-8")
    )["entity"]

    missing = []
    for description_type, descriptions in entity_descriptions.get_all_entity_description().items():
        domain = TRANSLATION_DOMAINS[description_type]
        for description in descriptions:
            if callable(description):
                continue
            key = description.translation_key or description.key
            if key not in translations.get(domain, {}):
                missing.append(f"{domain}.{key}")

    assert sorted(set(missing)) == []


def test_translation_placeholders_match_descriptions() -> None:
    """
    Every translated name uses exactly the placeholders its description passes.

    sensor_oven_water_tank (the oven-wide water tank, as opposed to the
    per-cavity sensor_oven_water_tank_group) had "{group_name}" in its en, de
    and zh-Hans name without passing a group_name, and Home Assistant logged
    "has translation placeholders '{}' which do not match the name" (#112).
    The oven-wide sensor_oven_current_temperature had the same slip in pl and
    zh-Hans.
    """
    translations_dir = Path("custom_components/homeconnect_ws/translations")
    translations = {
        path.name: json.loads(path.read_text(encoding="utf-8"))["entity"]
        for path in sorted(translations_dir.glob("*.json"))
    }

    mismatched = []
    for description_type, descriptions in entity_descriptions.get_all_entity_description().items():
        domain = TRANSLATION_DOMAINS[description_type]
        for description in descriptions:
            if callable(description):
                continue
            key = description.translation_key or description.key
            expected = set(description.translation_placeholders or {})
            for language, entities in translations.items():
                name = entities.get(domain, {}).get(key, {}).get("name")
                if name is None:
                    continue
                used = set(re.findall(r"{(\w+)}", name))
                if used != expected:
                    mismatched.append(f"{language}: {domain}.{key} uses {sorted(used)}")

    assert mismatched == []


def test_german_translation_complete() -> None:
    """
    de.json has every key en.json has.

    German is a required locale next to English: Germany has the most Home
    Assistant installations and is BSH's home market. Other languages are
    optional.
    """

    def flatten(node: dict, prefix: str = "") -> set[str]:
        keys = set()
        for key, value in node.items():
            if isinstance(value, dict):
                keys |= flatten(value, f"{prefix}{key}.")
            else:
                keys.add(f"{prefix}{key}")
        return keys

    translations_dir = Path("custom_components/homeconnect_ws/translations")
    english = json.loads((translations_dir / "en.json").read_text(encoding="utf-8"))
    german = json.loads((translations_dir / "de.json").read_text(encoding="utf-8"))

    assert sorted(flatten(english) - flatten(german)) == []


async def test_sync_time_button_sets_the_clock_to_local_time() -> None:
    """
    The clock button sets the appliance clock to HA's local time.

    The appliance wants a naive local timestamp; the library's set_datetime()
    drops the offset that dt_util.now() carries.
    """
    description = next(
        entity_description
        for entity_description in COMMON_ENTITY_DESCRIPTIONS["button"]
        if getattr(entity_description, "key", None) == "button_sync_time"
    )
    # No isinstance() check here - HA clones these classes at runtime, see
    # _resolve_description in entity_descriptions/__init__.py.
    assert description.entity == "BSH.Common.Setting.ApplianceDateTime"
    assert description.press_fn is not None

    local_now = datetime(2026, 9, 24, 10, 36, 9, 123456, tzinfo=ZoneInfo("Europe/Berlin"))
    appliance = Mock(set_datetime=AsyncMock())
    with patch(
        "custom_components.homeconnect_ws.entity_descriptions.common.dt_util.now",
        return_value=local_now,
    ):
        await description.press_fn(appliance)
    appliance.set_datetime.assert_awaited_once_with(local_now)


async def test_sync_time_button_with_local_time(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """An appliance with LocalTime instead of ApplianceDateTime gets the clock button too."""
    appliance = await mock_homeconnect_appliance(
        description={
            "setting": [
                {
                    "uid": 1,
                    "name": "BSH.Common.Setting.LocalTime",
                    "available": True,
                    "access": Access.READ_WRITE,
                }
            ]
        }
    )
    buttons = entity_descriptions.get_available_entities(appliance)["button"]
    sync_time = next(button for button in buttons if button.key == "button_sync_time")
    assert sync_time.entity == "BSH.Common.Setting.LocalTime"


DOOR_STATE = {
    "status": [
        {
            "access": "read",
            "available": True,
            "enumeration": {"0": "Open", "1": "Closed"},
            "uid": 256,
            "name": "BSH.Common.Status.DoorState",
        },
    ]
}


async def test_door_binary_sensor_when_open_or_closed(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """A door that's only open or closed gets a binary sensor only."""
    appliance = await mock_homeconnect_appliance(description=copy.deepcopy(DOOR_STATE))
    assert generate_door_sensor(appliance) is None
    door = generate_door_binary_sensor(appliance)
    assert door is not None
    assert door.key == "binary_sensor_door_state"


async def test_door_sensor_when_more_states(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """A door that can also be locked or ajar gets an enum sensor only."""
    device_description = copy.deepcopy(DOOR_STATE)
    device_description["status"][0]["enumeration"] = {
        "0": "Open",
        "1": "Closed",
        "2": "Locked",
        "3": "Ajar",
    }
    appliance = await mock_homeconnect_appliance(description=device_description)
    assert generate_door_binary_sensor(appliance) is None
    door = generate_door_sensor(appliance)
    assert door is not None
    assert door.key == "sensor_door_state"


@pytest.mark.parametrize(
    ("temperature_unit", "expected"),
    [
        (UnitOfTemperature.CELSIUS, ["number_setpoint_freezer", "number_oven_alarm"]),
        (
            UnitOfTemperature.FAHRENHEIT,
            ["number_setpoint_freezer_fahrenheit", "number_oven_alarm"],
        ),
    ],
)
def test_one_temperature_unit(temperature_unit: str, expected: list[str]) -> None:
    """A temperature reported in both units keeps the one in Home Assistant's unit."""
    descriptions = [
        HCNumberEntityDescription(key="number_setpoint_freezer", entity="Test.Setpoint"),
        HCNumberEntityDescription(
            key="number_setpoint_freezer_fahrenheit", entity="Test.SetpointFahrenheit"
        ),
        HCNumberEntityDescription(key="number_oven_alarm", entity="Test.Alarm"),
    ]

    kept = entity_descriptions._one_temperature_unit(descriptions, temperature_unit)

    assert [description.key for description in kept] == expected
    # The kept one can still follow the appliance to the other unit's entity
    assert kept[0].other_unit_entity == (
        "Test.SetpointFahrenheit"
        if temperature_unit == UnitOfTemperature.CELSIUS
        else "Test.Setpoint"
    )
    assert kept[1].other_unit_entity is None


@pytest.mark.parametrize(
    "temperature_unit", [UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT]
)
def test_one_temperature_unit_keeps_the_only_one(temperature_unit: str) -> None:
    """A temperature reported in one unit only keeps it, whatever Home Assistant's unit."""
    descriptions = [
        HCNumberEntityDescription(key="number_setpoint_freezer_fahrenheit"),
        HCNumberEntityDescription(key="number_setpoint_refrigerator"),
    ]

    kept = entity_descriptions._one_temperature_unit(descriptions, temperature_unit)

    assert kept == descriptions


async def test_temperature_unit_select_with_celsius_and_fahrenheit(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """An appliance that switches between Celsius and Fahrenheit gets a unit select."""
    appliance = await mock_homeconnect_appliance(
        description={
            "setting": [
                {
                    "access": "readwrite",
                    "available": True,
                    "enumeration": {"0": "Celsius", "1": "Fahrenheit"},
                    "uid": 4153,
                    "name": "BSH.Common.Setting.TemperatureUnit",
                },
            ]
        }
    )
    description = generate_temperature_unit(appliance)

    assert description is not None
    assert description.key == "select_temperature_unit"


async def test_no_temperature_unit_select_when_fixed(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """An appliance whose unit can never change (readstatic) gets no unit select."""
    appliance = await mock_homeconnect_appliance(
        description={
            "setting": [
                {
                    "access": "readstatic",
                    "available": True,
                    "enumeration": {"0": "Celsius", "1": "Fahrenheit"},
                    "uid": 4153,
                    "name": "BSH.Common.Setting.TemperatureUnit",
                },
            ]
        }
    )

    assert generate_temperature_unit(appliance) is None


def _status(uid: int, name: str, enumeration: dict[str, str] | None = None) -> dict:
    status: dict = {"access": "read", "available": True, "uid": uid, "name": name}
    if enumeration is not None:
        status["enumeration"] = enumeration
    return status


async def test_meatprobe_plugged_left_out_when_per_cavity(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """An oven reporting the probe per cavity gets no appliance-wide probe sensor."""
    appliance = await mock_homeconnect_appliance(
        description={
            "status": [
                _status(1, "Cooking.Oven.Status.MeatprobePlugged"),
                _status(2, "Cooking.Oven.Status.Cavity.340.MeatprobePlugged"),
            ]
        }
    )
    assert generate_meatprobe_plugged(appliance) is None

    appliance = await mock_homeconnect_appliance(
        description={"status": [_status(1, "Cooking.Oven.Status.MeatprobePlugged")]}
    )
    description = generate_meatprobe_plugged(appliance)
    assert description is not None
    assert description.key == "binary_sensor_oven_meatprobe_plugged"


DOOR_ENUM = {"0": "Open", "1": "Closed", "2": "Locked", "3": "Ajar"}
COMPARTMENT_ENUM = {"0": "Closed", "1": "Open"}


async def test_compartment_door_left_out_when_only_door(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """A single-door freezer's compartment door is the same door as its Door entity."""
    freezer_door = compartment_door(
        "binary_sensor_freezer_door_state", "Refrigeration.Common.Status.Door.Freezer"
    )
    appliance = await mock_homeconnect_appliance(
        description={
            "status": [
                _status(1, "BSH.Common.Status.DoorState", DOOR_ENUM),
                _status(2, "Refrigeration.Common.Status.Door.Freezer", COMPARTMENT_ENUM),
            ]
        }
    )
    assert freezer_door(appliance) is None


async def test_compartment_doors_kept_with_more_doors(
    mock_homeconnect_appliance: MockApplianceFactory,
) -> None:
    """A fridge-freezer keeps a door entity per compartment."""
    freezer_door = compartment_door(
        "binary_sensor_freezer_door_state", "Refrigeration.Common.Status.Door.Freezer"
    )
    appliance = await mock_homeconnect_appliance(
        description={
            "status": [
                _status(1, "BSH.Common.Status.DoorState", DOOR_ENUM),
                _status(2, "Refrigeration.Common.Status.Door.Freezer", COMPARTMENT_ENUM),
                _status(3, "Refrigeration.Common.Status.Door.Refrigerator", COMPARTMENT_ENUM),
            ]
        }
    )
    description = freezer_door(appliance)
    assert description is not None
    assert description.key == "binary_sensor_freezer_door_state"


@pytest.mark.parametrize(
    ("known", "entity", "alternates"),
    [
        ({"Test.OldName"}, "Test.OldName", None),
        ({"Test.NewName"}, "Test.NewName", None),
        ({"Test.OldName", "Test.NewName"}, "Test.OldName", ("Test.NewName",)),
    ],
)
def test_with_known_names(known: set[str], entity: str, alternates: tuple[str, ...] | None) -> None:
    """A feature under an old and a new name uses the ones the appliance knows."""
    description = HCSwitchEntityDescription(
        key="switch_test", entity="Test.OldName", alternate_entities=("Test.NewName",)
    )

    available = entity_descriptions._available_description("switch", description, known)

    assert available is not None
    assert available.entity == entity
    assert available.alternate_entities == alternates


def test_with_no_known_names() -> None:
    """A feature under names the appliance doesn't know gets no entity."""
    description = HCSwitchEntityDescription(
        key="switch_test", entity="Test.OldName", alternate_entities=("Test.NewName",)
    )

    assert entity_descriptions._available_description("switch", description, {"Other"}) is None
