# Adding a new Entity

New entities are added by adding an entity description in `entity_descriptions/[device type].py` (e.g. `cooking.py`, `dishcare.py`, `laundry_care.py`, `refrigeration.py`, `consumer_products.py`, or the shared `common.py`). See the [HA documentation on entity descriptions](https://developers.home-assistant.io/docs/core/entity?_highlight=description#entity-description) for the base concept.

This integration's entity classes are subclasses of the corresponding [HA Entity](https://developers.home-assistant.io/docs/core/entity) type. The description dataclasses (in `entity_descriptions/descriptions_definitions.py`) extend HA's own `*EntityDescription` for each platform with HC-specific fields. Base HA fields (`device_class`, `entity_category`, `native_min_value`, `native_max_value`, etc.) still apply and aren't repeated here — see the corresponding HA docs.

## Base Entity (`HCEntityDescription`)

Fields common to every entity type:

- `entity`: the name of the HC entity, e.g. `"BSH.Common.Status.DoorState"`
- `entities`: for entity types that watch more than one HC entity
- `available_access`: which `Access` values (`READ`, `READ_WRITE`, `WRITE_ONLY`) count as "available"; each platform sets its own sensible default

  There's one automatic exception to this: an `Option` or `SelectedProgram` entity (as opposed to a `Setting`) whose access is currently `READ` is always shown as available, and its platform's write action (`switch`/`select`/`number`) raises a clear `ServiceValidationError` instead of attempting a write it would reject. Home Connect appliances lock some Options to read-only while a program runs, and lock `SelectedProgram` itself while a delayed start is armed, rather than making them unavailable - the official app shows them as visible-but-disabled, not hidden - confirmed live on fork issue #59, both for a locked Option (an iDos dosing switch) and for `SelectedProgram` (a Bosch WGB244A0BY's own debug log shows its access flip `READ_WRITE` -> `READ` the moment a delayed start is armed and back once the wash actually starts). This only applies to `Access.READ`, not `Access.NONE` (which means "not applicable at all right now" and should stay genuinely unavailable), and it's automatic based on the underlying HC entity's own class - no entity description field controls it.

  Every `Option`- or `SelectedProgram`-backed entity also always carries a `readonly` extra state attribute (`true`/`false`) reflecting this, whether or not it's currently locked - not just when `true` - so a template or custom card can rely on it existing rather than treating a missing attribute as "not readonly" (feedback from issue #59). Entities that could never be either type (a plain sensor, a `Setting`-backed switch, etc.) don't get the attribute at all, since the concept doesn't apply to them.

- `extra_attributes`: list of dicts mapping an attribute `name` to an HC `entity` (and optionally a `value_fn`) to expose as extra state attributes, e.g.

  ```python
  extra_attributes = [
      {
          "name": "Is Estimated",
          "entity": "BSH.Common.Option.RemainingProgramTimeIsEstimated",
      }
  ]
  ```

- `clear_on_expected_offline`: for laundry appliances only — clears the entity's value to `None` instead of showing a stale reading while the appliance is in its expected-offline window (see [Known Limitations](../integration/support-and-troubleshooting.md#known-limitations) on the code-1000 clean-disconnect behavior)

## Select Entity (`HCSelectEntityDescription`)

- `has_state_translation`: set `True` if state translation strings are available
- `mapping`: dict mapping the HC program/option name to a display value (used by `HCProgram`)
- `force_option_when_expected_offline`: forces `current_option` to this value while the appliance is in its expected-offline window, instead of trusting a possibly-stale last-known value

> [!NOTE]
> `options` on `HCSelect` is computed live via a `@property`, not cached once at `__init__` — an `Option` entity's `.enum` isn't guaranteed to be populated by the time entities are constructed (unlike a `Setting`, which is static from the profile). Caching it once caused a hard crash on entity registration (`AttributeError` from HA core's own `SelectEntity.options`) the first time this was tried. If you're adding a new select and it isn't populated yet at startup, this is why — don't reintroduce an `__init__`-time cache without handling that case.

## Switch Entity (`HCSwitchEntityDescription`)

- `value_mapping`: mapping for non-boolean on/off values, e.g. `("On", "Off")`
- `force_off_when_expected_offline`: same idea as the select's `force_option_when_expected_offline`, but for a 2-state switch

## Sensor Entity (`HCSensorEntityDescription`)

- `has_state_translation`: set `True` if state translation strings are available
- `mapping`: dict mapping raw HC values to display values
- `force_option_when_expected_offline`: same idea as the select's field, for a read-only enum sensor

## Binary Sensor Entity (`HCBinarySensorEntityDescription`)

- `value_on`: set of values for which the sensor should be `on`, e.g. `{"Open", "Ajar"}`
- `value_off`: set of values for which the sensor should be `off`, e.g. `{"Closed", "Locked"}`

## Number Entity (`HCNumberEntityDescription`)

No HC-specific extra fields — use HA's own inherited `NumberEntityDescription` fields (`native_min_value`, `native_max_value`, `native_step`, etc.) directly, e.g. `native_max_value=99` to cap a value below what the appliance profile itself allows.

## Light Entity (`HCLightEntityDescription`)

- `brightness_entity`, `color_temperature_entity`, `color_entity`, `color_mode_entity`: names of the HC entities backing each of these light capabilities, when they're separate from the main `entity`

## Fan Entity (`HCFanEntityDescription`)

- `default_program`: the HC program name to start when the fan is turned on without an explicit speed/preset

## Update Entity (`HCUpdateEntityDescription`)

- `command_entity`: the HC entity used to trigger the install/download command

## Button, Event Sensor, and other types

- **Button** (`HCButtonEntityDescription`): no extra fields beyond the base ones.
- **Event Sensor**: turns multiple HC events into a single sensor. Required fields: `entities` (list of event entities, evaluated top to bottom until one is set) and `options` (list of display values, one more than the number of `entities` — the last option is the fallback when none are set).

## Development Options

This integration has development-only options for use with the [HomeConnect Websocket Simulator](https://github.com/vemboy200/homeconnect_ws_sim/) (a fork retargeted to depend on this project's [home-disconnect](https://github.com/vemboy200/home-disconnect) library instead of the unmaintained original). Set these in `configuration.yaml`:

```yaml
homeconnect_ws:
  # Allow creating new config entries from a Diagnostics dump
  setup_from_dump_enabled: True

  # Override the host in the config flow.
  override_host: "192.168.0.10"

  # Override the encryption key in the config flow. Encryption mode is
  # also forced to "TLS". Use together with the Simulator's "--psk" CLI arg.
  override_psk: "PSK_KEY"
```
