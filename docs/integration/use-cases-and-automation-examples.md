## Use Cases

- Monitor the multiple sensors of the appliance and trigger automations based on these sensors.
- Start programs on your appliances from your dashboard.
- Monitor the program status of the appliances.
- Control the light of your appliances.
- Adjust the appliance settings.

## Automation examples

Get started with these automation examples

### Periodically check for and install Home Connect firmware updates

Here's an example automation that occasionally reenables the cloud connection, checks for and installs a firmware update if one's available, then disables it again:

- **Trigger**: `time` trigger at `"03:00:00"`.
- **Conditions**: only runs on the 1st of the month (`now().day == 1`).
- **Actions**: turn on `switch.dishwasher_allow_cloud_connection` → wait up to 24 hours for an `update` entity to report one available → install it if found → wait up to 30 minutes for the install to finish → turn `switch.dishwasher_allow_cloud_connection` back off.

<details>
<summary>YAML example for periodically reconnecting the cloud to check for firmware updates</summary>
<br>

```yaml
alias: Periodically check for and install Home Connect firmware updates
description: >-
  Re-enables the appliance's cloud connection on the 1st of every month so it
  has a chance to check in, then downloads (if supported) and installs any
  available firmware update via the Update entities before disabling cloud
  access again.
triggers:
  - trigger: time
    at: "03:00:00"
conditions:
  - condition: template
    value_template: "{{ now().day == 1 }}"
actions:
  - action: switch.turn_on
    target:
      # Replace with your appliance's "Allow Cloud Connection" entity
      entity_id: switch.dishwasher_allow_cloud_connection
  - wait_template: >-
      {{ is_state('update.dishwasher_software_download', 'on')
         or is_state('update.dishwasher_software_update', 'on') }}
    timeout:
      hours: 24
    continue_on_timeout: true
  - if:
      # Skip if your appliance has no separate download stage
      - condition: state
        entity_id: update.dishwasher_software_download
        state: "on"
    then:
      - action: update.install
        target:
          entity_id: update.dishwasher_software_download
      - wait_template: "{{ is_state('update.dishwasher_software_download', 'off') }}"
        timeout:
          minutes: 30
        continue_on_timeout: true
  - if:
      - condition: state
        entity_id: update.dishwasher_software_update
        state: "on"
    then:
      - action: update.install
        target:
          entity_id: update.dishwasher_software_update
      - wait_template: "{{ is_state('update.dishwasher_software_update', 'off') }}"
        timeout:
          minutes: 30
        continue_on_timeout: true
  - action: switch.turn_off
    target:
      entity_id: switch.dishwasher_allow_cloud_connection
mode: single
```

</details>

### Send a notification when the appliance ends the program

- **Trigger**: `sensor.appliance_operation_state` changes to `finished`.
- **Actions**: `notify.notify` with a message that the program has finished.

<details>
<summary>YAML example for notifying when the appliance's program ends</summary>
<br>

```yaml
alias: "Notify when program ends"
triggers:
  - trigger: state
    entity_id:
      - sensor.appliance_operation_state
    to: finished
actions:
  - action: notify.notify
    data:
      message: "The appliance has finished the program."
```

</details>

### Start a program when electricity is cheap
[comment]: <> ( Also also stolen directly from the Core Home Connect integration)
Because electricity is typically cheaper at night, this automation will activate the silent mode when starting the program at night.

- **Trigger**: `sensor.electricity_price` drops to `"0.10"`.
- **Conditions**: `sensor.diswasher_door` is `closed`.
- **Actions**: `home_connect.set_program_and_options` — between `22:00` and `06:00`, starts the Eco 50 program with silent mode on; otherwise starts it without silent mode.

<details>
<summary>YAML example for starting a program when electricity is cheap</summary>
<br>
    
```yaml
alias: "Start program when electricity is cheap"
triggers:
  - trigger: state
    entity_id: sensor.electricity_price
    to: "0.10"
conditions:
  - condition: state
    entity_id: sensor.diswasher_door
    state: closed
actions:
  - if:
      - condition: time
        after: '22:00:00'
        before: '06:00:00'
    then:
      - action: home_connect.set_program_and_options
        data:
          device_id: "your_device_id"
          affects_to: "active_program"
          program: "dishcare_dishwasher_program_eco_50"
          dishcare_dishwasher_option_silence_on_demand: true
    else:
      - action: home_connect.set_program_and_options
        data:
          device_id: "your_device_id"
          affects_to: "active_program"
          program: "dishcare_dishwasher_program_eco_50"
```
</details>


### Keep the appliance clock right without internet access

An appliance cut off from the internet (e.g. blocked at the router) can't sync its clock and drifts by a few seconds a day. This automation sets the clock from Home Assistant once a night, so it stays right and picks up DST changes on its own. Both the button and the "Synchronize time with server" switch are disabled by default, so enable them on the device page first:

- **Trigger**: `time` trigger at `"04:00:00"` - after the DST switch, so the clock is right by morning.
- **Conditions**: the appliance's "Synchronize time with server" switch is off. While it's on, the appliance locks its clock (the button shows `readonly: true` and refuses to press).
- **Actions**: press the "Sync time from Home Assistant" button.

<details>
<summary>YAML example for keeping the appliance clock in sync</summary>
<br>

```yaml
alias: Keep the oven clock in sync with Home Assistant
description: >-
  Sets the appliance's clock to Home Assistant's local time once a night.
  Works fully offline and keeps DST changes right, since Home Assistant
  knows the time zone.
triggers:
  - trigger: time
    at: "04:00:00"
conditions:
  - condition: state
    # Replace with your appliance's "Synchronize time with server" entity -
    # the appliance won't accept a clock write while this is on
    entity_id: switch.oven_synchronize_time_with_server
    state: "off"
actions:
  - action: button.press
    target:
      # Replace with your appliance's "Sync time from Home Assistant" entity
      entity_id: button.oven_sync_time_from_home_assistant
mode: single
```

</details>
