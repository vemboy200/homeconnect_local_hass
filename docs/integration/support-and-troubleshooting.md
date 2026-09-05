## Known Limitations

- While this integration can (in theory) support all the functions supported in the Home Connect app, in reality, the functions have to reverse engineered
- The mDNS on Home Connect devices is wonky and fail to connect. The best example of this is that in the App, unless if the phone is on the same Wireless Access Point as the appliance theres a chance a local connection may fail to establish.
- Home Assistant may overload the device's local capacity causing it to not accept new connections for 24 hours. This is called a **Websocket Shutdown**. See [this section](#how-to-resolve-a-websocket-shutdown) for more info and how to resolve it.
- The Appliance must be online and reachable on your local network during initial setup. The config flow actively tests the connection before letting you finish adding the device, so it cannot be added while powered off or unreachable. Once added, the appliance can go offline/online freely and its entities will simply go unavailable and recover automatically. See issues <https://github.com/chris-mc1/homeconnect_local_hass/issues/274> and <https://github.com/chris-mc1/homeconnect_local_hass/issues/293> for info about why it is like this.
- Washing machines, dryers, and washer/dryer combos may disconnect from Wi-Fi entirely when powered off. This is normal behavior for these appliance types. If the appliance sent a clean disconnect (WebSocket close code 1000, meaning it deliberately cut its own Wi-Fi rather than dropping unexpectedly) right before going quiet, its entities stay available and keep reporting their last-known state through the outage instead of going `unavailable`. An abnormal drop (any other close code, or none seen yet) still correctly marks them unavailable, same as any other appliance. Behavior isn't consistent across models, and this isn't just a combo thing - one combo checked (WNC254A0BY, see the program-selection limitation below) stays connected while powered off, closer to the dishwasher pattern, while another combo (WDU28512) does drop offline like a standalone unit, and at least one standalone washer (Bosch WGB256ABSN) has also been confirmed to stay connected while off. So every washer, dryer, and combo gets the same lenient treatment, since it's harmless for a model that happens to stay connected. See [issue #7](https://github.com/vemboy200/homeconnect_local_hass/issues/7) and [issue #21](https://github.com/vemboy200/homeconnect_local_hass/issues/21) for the full discussion.
- On at least some Washer/Dryer/WasherDryer models, you cannot remotely **select** which program runs. Only the official Home Connect app can do that, even though the appliance's own profile file claims that resource is read-write. Starting, pausing, and otherwise controlling whatever program is already selected works fine from Home Assistant. Confirmed on a Bosch WNC254A0BY (WasherDryer). Unlike other unavailable states (e.g. an appliance being powered off), there's no state or schema field that predicts this ahead of time, the appliance stays connected, reports itself as writable, and the entity looks and behaves like a normal, working selector right up until you try to change it and get a rejection back. Practical workaround: pre-select the program you want via the app or the appliance's own dial, then use Home Assistant to trigger the actual start (e.g. at a cheap-energy price window) instead of trying to automate program choice too. See [issue #9](https://github.com/vemboy200/homeconnect_local_hass/issues/9) for the full investigation
- An entity that's permanently unavailable, regardless of appliance state, usually means the profile file declares a feature the appliance doesn't actually have - not a bug in the integration. Confirmed live: a "Fast preheat" entity, exclusive to electric ovens, showing up on a gas oven's own profile file. The fix is disabling that specific entity rather than reporting it. See [this discussion](https://github.com/vemboy200/homeconnect_local_hass/discussions/2#discussioncomment-18109110) for the full back-and-forth.
- Some switches, selects, and numbers get locked to read-only while a program is running (e.g. an iDos dosing switch on a washer) - the official Home Connect app shows these as visible but disabled rather than hiding them, and this integration does the same: the entity keeps showing its current value and gets a `readonly: true` attribute, and trying to change it raises a clear error instead of a silent failure. This is normal, appliance-driven locking, not a bug - see [issue #59](https://github.com/vemboy200/homeconnect_local_hass/issues/59) for the full investigation.

## Requesting a New Feature

**Entity coverage for the appliances the maintainer actually owns (Thermador dishwasher/oven/freezer) is essentially complete.** Since every entity has to be reverse engineered from a real appliance's profile (see [Known Limitations](#known-limitations)), there's no way to add entities for other appliances, brands, or models without someone who owns one providing their own profile dump. If you want support for a feature this integration doesn't have yet, submitting that data yourself (see below) isn't just helpful, it's the only way it happens.

Since this integration's functions have to be reverse engineered (see [Known Limitations](#known-limitations)), the more information you provide when requesting a new entity, the easier it is for a developer to add it. There are two ways to do this, depending on how much effort you want to put in.

### Basic method

1. Use the [Export Safe Profile](other-stuff.md#exporting-an-appliance-profile) option to get a ZIP with the two XML files, already renamed and with no sensitive data - safe to share as-is.
   - Alternatively, use the [Home Connect Profile Downloader](https://github.com/bruestel/homeconnect-profile-downloader) tool and manually remove the `.json` file (contains your encryption key - don't share it) and the MAC address segment from the two XML filenames.
2. Download the [Diagnostics](https://www.home-assistant.io/docs/configuration/troubleshooting/#download-diagnostics) of the appliance's Config Entry.
3. [Open a feature request](https://github.com/vemboy200/homeconnect_local_hass/issues/new?template=feature_request.yml) describing, in plain terms, the feature/entity you'd like added (e.g. "I want a sensor for my appliance's door state"), and attach the two XML files from the ZIP along with the Diagnostics.

### Advanced method

If you're comfortable digging a bit deeper, you can help pinpoint exactly which feature maps to the entity you want, which makes it much faster for a developer to add:

1. Follow steps 1-2 of the Basic method above.
2. [Enable debug logging](#enabling-debug-logging) for the integration.
3. Trigger the feature on the appliance itself (e.g. open the door, change a setting, start a program) and watch the debug log for the corresponding update message.
4. Note the UID logged for that update. It will be in **decimal**, while the UIDs inside the `*_DeviceDescription.xml`/`*_FeatureMapping.xml` files are in **hexadecimal**. Convert between the two to match them up. For example, on a Thermador oven, the live oven temperature in fahrenheit logs as UID `5959` (decimal), which is `1747` in hex, matching `Cooking.Oven.Status.Cavity.340.CurrentTemperatureFahrenheit` in the FeatureMapping file.
5. Include that UID/feature name (and what it corresponds to) in your issue, alongside everything from the Basic method, so developers know exactly which feature to wire up.

## Trouble Shooting

### Home Assistant cannot connect to my Appliance, what should I do?

If Home Assistant cannot connect to your appliance (during setup) despite correctly entering the right profile file and IP address, here are some tips:

- Try to see if Home Connect can establish a local connection on the same network as Home Assistant.
- To do this, open the Home Connect App, go to your appliance(s), then to its settings, then scroll down to the network section.
  - If you see the bottom line lit up green, this could mean two things:
    1. You have the wrong/outdated profile file. Make sure you have the correct file, and if it's outdated, get a new one.
    2. As noted in the known limitations, the mDNS on the device is wonky, and if mDNS fails, even a direct IP connection may fail.
  - If you don't see the bottom line lit up green, this could mean a few things:
    1. If you're on the same wireless access point as the device, your device is most likely offline or does not support a local connection.
    2. If you're not on the same wireless access point, make sure you are.
    3. The device may be offline; check it physically to see if there's no Wi-Fi signal indicator on it.
    4. If the device does have a Wi-Fi signal, then Home Assistant may have overloaded the device's local capacity, causing a websocket shutdown. See below on how to resolve it.

### How to resolve a websocket shutdown

This integration has built in measures (measures not fully tested yet) to prevent a websocket shutdown, however unexpectedly shutting down Home Assistant bypasses these measures. If enough unexpected shutdowns of Home Assistant happen, then Home Assistant will leave half-dead sessions that overload the device's session capacity, leading to a websocket shutdown.

Confirmed errors of a websocket shutdown seen so far (there may be others):
- A plain HTTP 404 on the WebSocket upgrade (`aiohttp.WSServerHandshakeError`) where the appliance's HTTP layer responds normally but rejects the upgrade itself. The cause is understood (unexpected Home Assistant shutdowns leaving half-dead sessions, as described above), and this integration already has a fix/mitigation for it.
- A TLS handshake reset, which this integration classifies as an authentication failure (`home_disconnect.errors.AuthenticationError`), is a confirmed cause of a shutdown on a washer/dryer combo. The actual cause of this one is still unknown, all that's confirmed is that a power cycle resolves it, not why it happens in the first place. Note that this same exception can also mean a wrong or outdated encryption key, not a websocket shutdown, so before you try the methods below, try getting a fresh profile file and using the [Update Profile File](other-stuff.md#reconfiguring-an-appliance) reconfigure option, which refreshes the encryption key without needing to remove and re-add the entry.

There are three ways to resolve a websocket shutdown:

1. Disable the cloud: Disabling the cloud (follow the protip section on how to do it), then waiting 24 hours, can allow the device to reopen its local websocket. Note that since you're doing this during a local websocket shutdown, the smart features of the device will be inoperable until the device reopens its websocket. The device will still stay connected to your Wi-Fi.
2. Power cycle the appliance: Cutting the power from your appliance for 1-5 minutes, then reapplying it, can help resolve the issue.
3. Re-pair the appliance (not recommended): Resetting the device's network settings and re-pairing it to the Home Connect App resolves the issue. However, doing that is time consuming, and you'll need to get a new profile file and apply it via the [Update Profile File](other-stuff.md#reconfiguring-an-appliance) reconfigure option, since re-pairing changes the appliance's encryption key.

### Reporting Issues and Bugs

- A full debug log of at least reloading the config entry and any actions leading to an error
- The [Diagnostics](https://www.home-assistant.io/docs/configuration/troubleshooting/#download-diagnostics) of the Config Entry
- For reports relating to adding a new Appliance: the `*_DeviceDescription.xml` and `*_FeatureMapping.xml` files from the Profile File

### Enabling debug logging

Use one of these two methods enable debug logging:

- Through the UI:
    1. [Enable Debug logging](<https://www.home-assistant.io/docs/configuration/troubleshooting>) on the detail page of the integration
    2. Reload the config entry
    3. Perform the actions that lead to an error
    4. [Disable Debug logging](https://www.home-assistant.io/docs/configuration/troubleshooting/#disable-debug-logging-and-download-logs) on the detail page of the integration

- OR -

- Through configuration.yaml:
    1. Add the following to your [configuration.yaml](https://www.home-assistant.io/docs/configuration/) file:

        ```yaml
        logger:
        logs:
            custom_components.homeconnect_ws: debug # Home Connect Local Integration
            homeconnect_ws: debug
            home_disconnect: debug # home-disconnect Python package
        ```

    2. Restart Home Assistant
    3. Perform the actions that lead to an error
    4. Click the button below or navigate to "Settings" -> "Logs".

        [![Open your Home Assistant instance and show your Home Assistant logs.](https://my.home-assistant.io/badges/logs.svg)](https://my.home-assistant.io/redirect/logs/?)

    5. Download the log file using download button on the left
