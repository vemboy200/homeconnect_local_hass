## Reconfiguring an Appliance

Once an appliance is set up, you can reconfigure it from Settings → Devices & Services → Home Connect Local → the appliance's device page → gear/settings icon → Reconfigure. Two independent options are available:

- **Change Connection**: tries automatic (mDNS) discovery first, the same as initial setup, and only asks for a fixed IP-Address if that fails. Use this if mDNS isn't reachable on your network (pins a fixed IP-Address), or to move back to automatic discovery after a network change.
- **Update Profile File**: refresh this appliance's profile, either by uploading a new profile file or by signing in with Home Connect again - same two options as initial setup. Use this after a firmware update added new Options/Settings not present in your original profile, or after unpairing and re-pairing the appliance with Home Connect (which changes its encryption key).

## Exporting an Appliance Profile

Once an appliance is set up, you can export its profile from Settings → Devices & Services → Home Connect Local → the appliance's device page → gear/settings icon:

- **Export Safe Profile**: the two XML files (renamed to `{brand}_{model}`, no encryption key or other sensitive data), delivered as a download link in a notification. This is what you want for [Requesting a New Feature](support-and-troubleshooting.md#requesting-a-new-feature).
- **Export Full Profile**: the same two XML files plus the local encryption key, in the same shape as the Profile Downloader ZIP (re-importable via Upload Profile File). Meant for transferring an appliance to another system - not just Home Assistant, but other local-control projects like [openHAB's Home Connect Direct Binding](https://community.openhab.org/t/home-connect-direct-binding-no-cloud/160857) or the [Homey Home Connect (Local) app](https://homey.app/en-us/app/codes.lucasvdh.homeconnect/Home-Connect-(Local)/test/) - not something most users need. Written to a `homeconnect_ws_export` folder in your config directory rather than offered as a download link, since a link to a file containing your encryption key would be a real (if brief) exposure window - retrieve it via Samba, SSH, or another file-access method.

> [!NOTE]
> Two things noticed so far that aren't specific to this integration:
> - The Safe export's download link didn't work in the Arc desktop browser (opened fine on mobile Safari) - if a link doesn't work, try a different browser.
> - Home Assistant's File Editor add-on's own download button returned a 401 error trying to retrieve the Full export file. A Samba share worked without issue. If File Editor's download button fails for you too, use Samba (or SSH) instead.

## Data Updates

This integration is almost entirely push based, receiving updates from the appliance the moment something happens to it. Post setup, this integration can work completely offline, unlike the Home Connect app.

The one exception is the Wi-Fi Signal Strength sensor. The entity can only be polled from the appliance, so that entity is polled once an hour instead. It is polled infrequently due to the fact appliances dont move.

## Actions

This integration provides the following actions:

- `homeconnect_ws.start_program`: Start the currently selected program. Optionally set a start delay and/or a target finish time.
- `homeconnect_ws.set_start_in`: Set the start delay of the currently selected program.
- `homeconnect_ws.set_finish_in`: Set the target finish time of the currently selected program.

## Integration Removal

This integration follows standard integration removal, no extra steps are required.
1. Select the Config entry you want to delete
2. Click the 3 dots in the top right of the entry
3. Click the delete button
