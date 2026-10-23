"""Description for BSH.Common Entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from home_disconnect.entities import Access, Execution
from home_disconnect.keys import (
    CommandKey,
    EventKey,
    OptionKey,
    ProgramKey,
    RootKey,
    SettingKey,
    StatusKey,
)
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.components.number import NumberDeviceClass, NumberMode
from homeassistant.components.sensor import (
    SensorDeviceClass,
)
from homeassistant.components.switch.const import SwitchDeviceClass
from homeassistant.components.update import UpdateDeviceClass
from homeassistant.const import (
    EntityCategory,
    UnitOfTime,
)
from homeassistant.util import dt as dt_util

from custom_components.homeconnect_ws.helpers import delay_start_entity

from .descriptions_definitions import (
    HCBinarySensorEntityDescription,
    HCButtonEntityDescription,
    HCNumberEntityDescription,
    HCSelectEntityDescription,
    HCSwitchEntityDescription,
    HCUpdateEntityDescription,
    _EntityDescriptionsDefinitionsType,
)

if TYPE_CHECKING:
    from home_disconnect import Appliance


POWER_SWITCH_VALUE_MAPINGS = (
    ("On", "MainsOff"),
    ("Standby", "MainsOff"),
    ("On", "Off"),
    ("On", "Standby"),
    ("Standby", "Off"),
)

# BSH appliances name their powered-down PowerState value either "Off" or
# "MainsOff" depending on the model (see POWER_SWITCH_VALUE_MAPINGS above,
# which already accounts for both). Checked in this order so "Off" wins if
# an appliance's enum somehow had both.
POWER_OFF_STATE_NAMES = ("Off", "MainsOff")


def generate_start_button(appliance: Appliance) -> HCButtonEntityDescription | None:
    """Get Start Button description."""
    # SELECT_ONLY needs this button just as much as SELECT_AND_START: selecting
    # a program (writing SelectedProgram) only stages it and its options on
    # these appliances, it doesn't start anything - a separate write to
    # ActiveProgram is what actually starts it, and Program.start() already
    # posts there unconditionally regardless of execution type. Confirmed
    # live on fork issue #21 via the official cloud integration's own debug
    # log: "PUT .../programs/active {'key': '<program>'}" is the literal
    # start action, distinct from the earlier "PUT .../programs/selected"
    # that only configured options.
    #
    # Permissive by default (exclude only confirmed START_ONLY), not
    # restrictive: this generator runs once, synchronously, before the
    # appliance connection is even attempted (get_available_entities() is
    # called before coordinator.async_config_entry_first_refresh() - see
    # __init__.py) - for laundry appliances, whose setup is deliberately
    # non-blocking, that can mean *no* live data has arrived yet at all.
    # program.execution then reads whatever the static profile export
    # defaults to, which is frequently the placeholder "none" (confirmed on
    # fork issue #21's own washer - every program in a real profile export
    # showed execution="none", not the appliance's real value). Requiring a
    # positive SELECT_AND_START/SELECT_ONLY match meant the button silently
    # never got created for the rest of the session whenever this ran before
    # the real value arrived. HCStartButton.available is a live property and
    # correctly reflects the true execution type once data does arrive, so
    # the only actual cost of over-including here is a harmless extra button
    # on a genuinely START_ONLY appliance - far cheaper than a required
    # button silently missing for the whole session.
    programs = list(
        filter(
            lambda program: program.execution != Execution.START_ONLY,
            appliance.programs.values(),
        )
    )
    if len(programs) > 0:
        return HCButtonEntityDescription(
            key="button_start_program",
            entity=RootKey.BSH_COMMON_ACTIVE_PROGRAM,
            # HCStartButton.available reads appliance.selected_program, which
            # resolves through SelectedProgram, not ActiveProgram - without
            # this, the button only re-renders when ActiveProgram itself
            # changes, so live power-on/off toggling (which updates
            # SelectedProgram) can leave the displayed availability a step
            # stale until something else happens to touch ActiveProgram.
            # Confirmed live on fork issue #54.
            entities=[RootKey.BSH_COMMON_SELECTED_PROGRAM],
        )
    return None


def generate_delay_start(appliance: Appliance) -> HCNumberEntityDescription | None:
    """
    Get the "Delay start" number description.

    Offered whenever the appliance has StartInRelative or FinishInRelative.
    Its value is the delay itself and lives in HA, not on the appliance: some
    appliances accept the delay only as an option of the program start (#146),
    so the Start button applies it then.
    """
    entity = delay_start_entity(appliance)
    if entity is None:
        return None
    return HCNumberEntityDescription(
        key="number_delay_start",
        translation_key="number_delay_start",
        entity=entity.name,
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        native_min_value=0,
        mode=NumberMode.BOX,
    )


def _settable_power_states(appliance: Appliance) -> list[str] | None:
    """
    Return the PowerState values the appliance can be set to, if it has one.

    In the appliance's own order, so the select's options don't reorder
    between restarts.
    """
    entity = appliance.entities.get(SettingKey.BSH_COMMON_POWER_STATE)
    if entity is None:
        return None
    entity_min = getattr(entity, "min", None)
    entity_max = getattr(entity, "max", None)
    return [
        value
        for key, value in sorted((entity.enum or {}).items(), key=lambda item: int(item[0]))
        if entity_min is None or entity_max is None or entity_min <= int(key) <= entity_max
    ]


def _power_switch_mapping(states: list[str]) -> tuple[str, str] | None:
    """Return the switch's (on, off) pair, if the states are exactly one."""
    return next(
        (mapping for mapping in POWER_SWITCH_VALUE_MAPINGS if set(states) == set(mapping)), None
    )


def generate_power_switch(appliance: Appliance) -> HCSwitchEntityDescription | None:
    """
    Get the Power switch description.

    Power gets one entity: a switch when the appliance switches between two
    states (on and off, or on and standby), and a select for anything else
    (generate_power_select). There's no read-only sensor: while the appliance
    locks its power state, the switch or select shows it read-only, like the
    Home Connect app does. The profile's access can't decide this, since a
    profile marking it "read" doesn't mean it stays that way (fork issue #7's
    washer was turned off through it).
    """
    states = _settable_power_states(appliance)
    if states is None or (mapping := _power_switch_mapping(states)) is None:
        return None
    return HCSwitchEntityDescription(
        key="switch_power_state",
        entity=SettingKey.BSH_COMMON_POWER_STATE,
        device_class=SwitchDeviceClass.SWITCH,
        value_mapping=mapping,
        # MainsOff, Standby (when "On" is the on side) and Off all
        # mean not on, even the ones the switch never sets.
        on_values=tuple(sorted({mapping[0], "On"})),
        force_off_when_expected_offline=True,
    )


def generate_power_select(appliance: Appliance) -> HCSelectEntityDescription | None:
    """Get the Power select description, for a power state that isn't a switch."""
    states = _settable_power_states(appliance)
    if states is None or _power_switch_mapping(states) is not None:
        return None
    return HCSelectEntityDescription(
        key="select_power_state",
        entity=SettingKey.BSH_COMMON_POWER_STATE,
        options=[value.lower() for value in states],
        has_state_translation=True,
        force_option_when_expected_offline=_power_off_option(states),
    )


def _power_off_option(states: list[str]) -> str | None:
    """
    Return the option for powered off, if the appliance has one.

    "off" is only a valid option if this appliance's PowerState actually has
    Off/MainsOff - forcing to a name that isn't one of its real options makes
    SelectEntity.state fall back to None (shown as "Unknown"), confirmed live
    on fork issue #7.
    """
    return next((name.lower() for name in POWER_OFF_STATE_NAMES if name in states), None)


def door_state_count(appliance: Appliance) -> int | None:
    """Return how many states the door has, if the appliance reports one."""
    entity = appliance.entities.get(StatusKey.BSH_COMMON_DOOR_STATE)
    return None if entity is None else len(entity.enum or {})


def generate_door_binary_sensor(appliance: Appliance) -> HCBinarySensorEntityDescription | None:
    """
    Get the Door binary sensor description.

    Door gets one entity: a binary sensor when the door is only open or
    closed, and an enum sensor when it has more states (e.g. locked or ajar),
    which a binary sensor can't tell apart (generate_door_sensor).
    """
    count = door_state_count(appliance)
    if count is None or count > 2:
        return None
    return HCBinarySensorEntityDescription(
        key="binary_sensor_door_state",
        entity=StatusKey.BSH_COMMON_DOOR_STATE,
        device_class=BinarySensorDeviceClass.DOOR,
        value_on={"Open", "Ajar"},
        value_off={"Closed", "Locked"},
    )


def program_names(appliance: Appliance) -> dict[str, str]:
    """Return each program's name, sorted by program."""
    favorites = {
        f"BSH.Common.Program.Favorite.{favorite}": favorite
        for favorite in appliance.group_ids(ProgramKey.BSH_COMMON_FAVORITE)
    }

    programs = {}

    for program in appliance.programs:
        if (favorite := favorites.get(program)) is not None:
            favorite_name_entity = appliance.settings.get(
                f"BSH.Common.Setting.Favorite.{favorite}.Name"
            )
            if favorite_name_entity and favorite_name_entity.value:
                program_name = favorite_name_entity.value
            else:
                program_name = f"favorite_{favorite}"
        else:
            program_name = program.lower().replace(".", "_")

        programs[program] = program_name

    # sort programs
    programs_keys = list(programs.keys())
    programs_keys.sort()
    return {i: programs[i] for i in programs_keys}


def generate_program(appliance: Appliance) -> HCSelectEntityDescription | None:
    """Get the Program select description."""
    if not (programs := program_names(appliance)):
        return None
    return HCSelectEntityDescription(
        key="select_program",
        entity=RootKey.BSH_COMMON_SELECTED_PROGRAM,
        has_state_translation=False,
        mapping=programs,
    )


def generate_temperature_unit(appliance: Appliance) -> HCSelectEntityDescription | None:
    """
    Get Temperature unit description.

    Left out when the appliance's unit is fixed (Access.READ_STATIC, e.g. some
    ovens), where the select could never be changed. Temperature entities still
    follow the unit either way (see HCEntity).
    """
    entity = appliance.entities.get(SettingKey.BSH_COMMON_TEMPERATURE_UNIT)
    if entity and entity.access is not Access.READ_STATIC and len(entity.enum or {}) >= 2:
        return HCSelectEntityDescription(
            key="select_temperature_unit",
            entity=SettingKey.BSH_COMMON_TEMPERATURE_UNIT,
            device_class=SensorDeviceClass.ENUM,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        )
    return None


def generate_software_download_update(
    appliance: Appliance,
) -> HCUpdateEntityDescription | None:
    """Get Software Download update description, if a separate download stage exists."""
    if (
        EventKey.BSH_COMMON_SOFTWARE_DOWNLOAD_AVAILABLE in appliance.entities
        and CommandKey.BSH_COMMON_ALLOW_SOFTWARE_DOWNLOAD in appliance.entities
    ):
        return HCUpdateEntityDescription(
            key="update_software_download",
            entity=EventKey.BSH_COMMON_SOFTWARE_DOWNLOAD_AVAILABLE,
            command_entity=CommandKey.BSH_COMMON_ALLOW_SOFTWARE_DOWNLOAD,
            device_class=UpdateDeviceClass.FIRMWARE,
            entity_category=EntityCategory.CONFIG,
        )
    return None


def generate_software_update(appliance: Appliance) -> HCUpdateEntityDescription | None:
    """Get Software Update (install) description."""
    if (
        EventKey.BSH_COMMON_SOFTWARE_UPDATE_AVAILABLE in appliance.entities
        and CommandKey.BSH_COMMON_ALLOW_SOFTWARE_UPDATE_LOCAL_WI_FI in appliance.entities
    ):
        return HCUpdateEntityDescription(
            key="update_software_update",
            entity=EventKey.BSH_COMMON_SOFTWARE_UPDATE_AVAILABLE,
            command_entity=CommandKey.BSH_COMMON_ALLOW_SOFTWARE_UPDATE_LOCAL_WI_FI,
            device_class=UpdateDeviceClass.FIRMWARE,
            entity_category=EntityCategory.CONFIG,
        )
    return None


COMMON_ENTITY_DESCRIPTIONS: _EntityDescriptionsDefinitionsType = {
    "button": [
        HCButtonEntityDescription(
            key="button_abort_program",
            entity=CommandKey.BSH_COMMON_ABORT_PROGRAM,
        ),
        HCButtonEntityDescription(
            key="button_pause_program",
            entity=CommandKey.BSH_COMMON_PAUSE_PROGRAM,
        ),
        HCButtonEntityDescription(
            key="button_resume_program",
            entity=CommandKey.BSH_COMMON_RESUME_PROGRAM,
        ),
        HCButtonEntityDescription(
            key="button_mains_power_off",
            entity=CommandKey.BSH_COMMON_MAINS_POWER_OFF,
        ),
        HCButtonEntityDescription(
            key="button_deactivate_remote_control",
            entity=CommandKey.BSH_COMMON_DEACTIVATE_REMOTE_CONTROL,
            entity_category=EntityCategory.CONFIG,
            # One press locks Home Assistant out until it's turned on at the appliance
            entity_registry_enabled_default=False,
        ),
        HCButtonEntityDescription(
            key="button_deactivate_remote_control_start",
            entity=CommandKey.BSH_COMMON_DEACTIVATE_REMOTE_CONTROL_START,
            entity_category=EntityCategory.CONFIG,
            # One press locks Home Assistant out until it's turned on at the appliance
            entity_registry_enabled_default=False,
        ),
        HCButtonEntityDescription(
            key="button_sync_time",
            entity=SettingKey.BSH_COMMON_APPLIANCE_DATE_TIME,
            # The clock on appliances without ApplianceDateTime (upstream #504)
            alternate_entities=(SettingKey.BSH_COMMON_LOCAL_TIME,),
            entity_category=EntityCategory.CONFIG,
            # Only useful with "Synchronize time with server" off, which is
            # itself disabled by default, so follow it.
            entity_registry_enabled_default=False,
            press_fn=lambda appliance: appliance.set_datetime(dt_util.now()),
        ),
        HCButtonEntityDescription(
            key="button_stopwatch_start_pause_resume",
            entity=CommandKey.BSH_COMMON_STOP_WATCH_START_PAUSE_RESUME,
        ),
        HCButtonEntityDescription(
            key="button_stopwatch_reset",
            entity=CommandKey.BSH_COMMON_STOP_WATCH_RESET,
        ),
    ],
    "binary_sensor": [
        generate_door_binary_sensor,
        HCBinarySensorEntityDescription(
            key="binary_sensor_aqua_stop",
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity=EventKey.BSH_COMMON_AQUA_STOP_OCCURED,
            entity_registry_enabled_default=False,
            value_on={"Present"},
            value_off={"Off", "Confirmed"},
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_low_water_pressure",
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity=EventKey.BSH_COMMON_LOW_WATER_PRESSURE,
            entity_registry_enabled_default=False,
            value_on={"Present"},
            value_off={"Off", "Confirmed"},
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        HCBinarySensorEntityDescription(
            key="binary_remote_start_allowed",
            entity=StatusKey.BSH_COMMON_REMOTE_CONTROL_START_ALLOWED,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_confirm_permanent_remote_start",
            entity=EventKey.BSH_COMMON_CONFIRM_PERMANENT_REMOTE_START,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_program_aborted",
            entity=EventKey.BSH_COMMON_PROGRAM_ABORTED,
            entity_category=EntityCategory.DIAGNOSTIC,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_program_finished",
            entity=EventKey.BSH_COMMON_PROGRAM_FINISHED,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_interior_illumination",
            entity=StatusKey.BSH_COMMON_INTERIOR_ILLUMINATION_ACTIVE,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_alarm_clock_elapsed",
            entity=EventKey.BSH_COMMON_ALARM_CLOCK_ELAPSED,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_favorite_001",
            entity=EventKey.BSH_COMMON_FAVORITE_001_EXTERNAL_TRIGGER,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_favorite_002",
            entity=EventKey.BSH_COMMON_FAVORITE_002_EXTERNAL_TRIGGER,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_local_control_active",
            entity=StatusKey.BSH_COMMON_LOCAL_CONTROL_ACTIVE,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_remote_control_active",
            entity=StatusKey.BSH_COMMON_REMOTE_CONTROL_ACTIVE,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_backend_connected",
            entity=StatusKey.BSH_COMMON_BACKEND_CONNECTED,
            device_class=BinarySensorDeviceClass.CONNECTIVITY,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_software_update_successful",
            entity=EventKey.BSH_COMMON_SOFTWARE_UPDATE_SUCCESSFUL,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
        HCBinarySensorEntityDescription(
            key="binary_sensor_customer_service_request",
            entity=EventKey.BSH_COMMON_CUSTOMER_SERVICE_REQUEST,
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_category=EntityCategory.DIAGNOSTIC,
            # Feeds the appliance's Problem sensor instead
            entity_registry_enabled_default=False,
            value_on={"Present", "Confirmed"},
            value_off={"Off"},
        ),
    ],
    "select": [
        generate_power_select,
        HCSelectEntityDescription(
            key="select_remote_control_level",
            entity=SettingKey.BSH_COMMON_REMOTE_CONTROL_LEVEL,
            entity_category=EntityCategory.CONFIG,
            has_state_translation=True,
        ),
        # cleanup: duplicate select_remote_control_level entry removed
        HCSelectEntityDescription(
            key="select_time_format",
            entity=SettingKey.BSH_COMMON_TIME_FORMAT,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_date_format",
            entity=SettingKey.BSH_COMMON_DATE_FORMAT,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        HCSelectEntityDescription(
            key="select_weight_unit",
            entity=SettingKey.BSH_COMMON_WEIGHT_UNIT,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            has_state_translation=True,
        ),
        # The languages differ per appliance, so their names are shown as the appliance reports them
        HCSelectEntityDescription(
            key="select_language",
            entity=SettingKey.BSH_COMMON_LANGUAGE,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
        ),
        generate_temperature_unit,
    ],
    "start_button": [generate_start_button],
    "delay_start": [generate_delay_start],
    "switch": [
        generate_power_switch,
        # Dishwashers and dryers both have Half load, under their own names
        HCSwitchEntityDescription(
            key="switch_half_load",
            entity=OptionKey.DISHCARE_DISHWASHER_HALF_LOAD,
            alternate_entities=(OptionKey.LAUNDRY_CARE_DRYER_HALF_LOAD,),
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_child_lock",
            entity=SettingKey.BSH_COMMON_CHILD_LOCK,
            device_class=SwitchDeviceClass.SWITCH,
        ),
        HCSwitchEntityDescription(
            key="switch_allow_backend_connection",
            entity=SettingKey.BSH_COMMON_ALLOW_BACKEND_CONNECTION,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
        ),
        HCSwitchEntityDescription(
            key="switch_allow_consumer_insights",
            entity=SettingKey.BSH_COMMON_ALLOW_CONSUMER_INSIGHTS,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
        ),
        HCSwitchEntityDescription(
            key="switch_synchronize_with_time_server",
            entity=SettingKey.BSH_COMMON_SYNCHRONIZE_WITH_TIME_SERVER,
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
        ),
    ],
    "number": [
        HCNumberEntityDescription(
            key="number_duration",
            entity=OptionKey.BSH_COMMON_DURATION,
            device_class=NumberDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            mode=NumberMode.AUTO,
            clear_on_expected_offline=True,
        ),
        HCNumberEntityDescription(
            key="number_setting_alarm_clock",
            translation_key="number_setting_alarm_clock",
            entity=SettingKey.BSH_COMMON_ALARM_CLOCK,
            device_class=NumberDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            native_max_value=86400,  # 24 hours, matching the Home Connect App's limit
            mode=NumberMode.BOX,
        ),
    ],
    "update": [generate_software_download_update, generate_software_update],
    "program": [generate_program],
}
