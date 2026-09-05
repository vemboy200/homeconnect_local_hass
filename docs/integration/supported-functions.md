The following entities are available. Which ones appear depends on the appliance type and its feature set. Not every device supports every entity listed here.

## Supported across multiple kinds of appliances

| Entity | Type | Description |
| --- | --- | --- |
| Active Program | Sensor | Currently running program |
| Operation State | Sensor | Device state (e.g. Ready, Running, Finished) |
| Remaining Program Time | Sensor | Time left in the current program |
| Program Progress | Sensor | Progress as a percentage |
| Start In | Sensor / Number | Delay before the program starts |
| Finish In | Sensor / Number | Target time until the program finishes |
| Select Program | Select | Choose a program to run, may not be writeable on laundry machines |
| Start / Abort / Pause / Resume | Button | Control the active program |
| Power State | Switch / Select | Turn the appliance on or off |
| Child Lock | Switch | Lock the physical controls |
| Remote Start Allowed | Binary Sensor | Whether remote control is enabled on the device |
| Door State | Binary Sensor / Sensor | Whether the door is open or closed |
| Program Finished | Binary Sensor | Turns on when the current cycle completes |
| Wi-Fi Signal Strength | Sensor | Device's Wi-Fi signal strength - polled hourly (see Data Updates), not pushed like everything else |
| Cloud Connection | Binary Sensor | Whether the appliance is currently connected to the Home Connect cloud |
| Allow Cloud Connection | Switch | Enable or disable the appliance's connection to the Home Connect cloud |
| Allow Consumer Insights | Switch | Enable or disable usage data collection by the Home Connect cloud |
| Synchronize Time with Server | Switch | Whether the appliance keeps its clock in sync with a time server |
| Time Format | Select | 12-hour or 24-hour clock display |
| Software Update | Update | Tracks/triggers installing an available firmware update |
| Software Download | Update | Tracks/triggers downloading an available firmware update (only on appliances that support a separate download stage) |

A few additional diagnostic entities (Local Control Active, Remote Control Active) are also available, disabled by default.

The Home Connect protocol only signals that a firmware update exists, not which version it is, so the Update entities show a generic "New Version" placeholder rather than a real version number when one is available. Also, as mentioned before, if you disabled cloud access for your appliance, or it cannot reach the Home Connect Cloud, then it cannot get new firmware updates.

Some entites are excluded from this integration on purpose, even though the Home Connect Protocol Supports it

| Entity/featureDescription | UID (hex) | Reason for exclusion |
| --- | --- | --- |
|BSH.Common.Command.ApplyFactoryReset|0229|Irreversible change|
|BSH.Common.Command.ApplyNetworkReset|022A|Also an irreversible change|
|BSH.Common.Command.DeactivateWiFi|0001|Reversible, but will prevent HA from accessing the appliance until physically activated again|

## Dishwasher

- Wash program selection and options
  - Half load, hygiene plus, extra dry, extra rinse, speed-on-demand, silence-on-demand, sanitize
- FlexSpray zone configuration
  - Configure which FlexSpray zones are active for a wash
- Rinse aid and salt level sensors
  - Reports remaining rinse aid and salt levels
- Maintenance reminders
  - Filter check, machine care, smart filter
- Water hardness and rinse aid dose settings
  - Configure water hardness and how much rinse aid is dispensed
- Auto power off
  - Automatically turns the dishwasher off after a cycle finishes
- Time light (floor projector)
  - Projects the remaining time onto the floor

## Washing Machine / Dryer

- Program options
  - Temperature, spin speed, prewash, rinse plus, gentle cycle, hygienic steam
- iDos automatic dosing (levels 1 & 2)
  - Automatic detergent dosing levels
- Drum light and door ring LED control
  - Brightness and color mode
- Anti-wrinkle guard
  - Keeps tumbling laundry after a cycle ends to prevent wrinkles
- Maintenance reminders
  - Drum clean, lint filter full
- Condensate container alert (dryer)
  - Alerts when the condensate/water container needs emptying

## Oven

- Oven current and setpoint temperature
  - Live cavity temperature and the target temperature
- Meat probe temperature and plugged-in status
  - Live meat probe reading and whether it's plugged in
- Heating mode selection
  - Choose the oven's heating mode (e.g. top/bottom heat, convection)
- Fast preheat
  - Speeds up preheating to the target temperature
- Sabbath mode
  - Disables automatic timers/notifications for Sabbath observance
- Convection conversion
  - Automatically adjusts temperature/time when converting a recipe to convection
- Dim display on standby
  - Dims the oven's display when idle
- Clock display (analogue/digital)
  - Switch the oven's clock face between analogue and digital
- Night-time display dimming
  - Dims the display further during a configured night-time window
- Sound volume
  - Volume of the oven's button/alert sounds
- Telescopic slide-out rail
  - Controls/reports the telescopic rack rail
- Brand logo display
  - Toggle whether the brand logo shows on the display

## Hob

- Automatic timer
  - Time (minutes) after which a zone turns off automatically
- Automatic keylock
  - Defines if keylock (childlock) is turned on automatically, manually or turned off completely
- BridgeZoneMode
  - When turning on hob this indicates if some zone (pre defined) are joined or split
- EnergyConsumptionIndication
  - Indicates if energy consumption (kWh) shall be displayed after hob is turned off
- PowerManagement
  - Maximum power drain (off or 1000W up to 9000W; 500W steps)
- BuzzerBeepLevel
  - Which signal types shall be played
- EndTimerSignalduration
  - Signal duration after timer runs out
- Ventilation level
- Those are only available if paired with a hood:
  - HoodAutomaticLightOff
    - When hob is turned off then also turn off hood light
  - HoodAutomaticLightOn
    - When hob is turned on then also turn on hood light
  - HoodAutomaticStart
    - When hob is turned on then also turn on hood fan
  - HoodAfterRun
    - When hob is turned off then also keep hood fan running (or not)

## Hood

- Hood fan speed control
  - Set the fan speed/stage
  - Boost mode
- Ambient and work lighting
  - Control the hood's ambient and work lights
- Automatic shutoff delay
  - Keeps the fan running for a set time after being turned off
- Interval ventilation
  - Periodically runs the fan for a short interval
- Grease and carbon filter saturation sensors and one-tap reset buttons
  - Reports filter saturation and lets you reset the counter after cleaning/replacing

## Coffee Maker

- Bean container and amount
  - Remaining bean level
- Grind coarseness
  - Coffee grind coarseness setting
- Coffee strength
  - Brew strength setting
- Temperature
  - Brew temperature setting
- Brew size
  - Cup/brew size setting
- Shot count
  - Number of espresso shots
- Milk ratio
  - Milk-to-coffee ratio for milk-based drinks
- Cup warmer
  - Turn the cup warmer plate on or off
- Maintenance countdowns
  - Cleaning, descaling, water filter replacement
- Water tank and drip tray level sensors
  - Reports water tank and drip tray fill/empty state
- Per-drink brew counters
  - Coffee, espresso, milk-based drinks, and more

## Refrigerator / Freezer

- Fridge, freezer, and chiller setpoint temperatures (°C and °F)
  - Set and monitor target temperatures per compartment
- Door open and door alarm binary sensors
  - Reports whether a door is open, and whether the door-open alarm is active
- Super-freeze and super-cool modes
  - Temporarily maximizes cooling for fresh loads
- Eco, vacation, and fresh-food modes
  - Preset operating modes for efficiency, extended absence, or fresh food
- Interior light with brightness control
  - Control the interior light and its brightness
- Water filter alert
  - Alerts when the water filter needs replacing
- Sabbath mode duration
  - How long Sabbath mode stays active
