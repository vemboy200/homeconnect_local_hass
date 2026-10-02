# Idea: emulating the cloud during initial pairing, to remove the last internet dependency

**Status: this is an unclaimed idea, and not something thats being worked on.** This is a write-up for anyone who wants to pick it up, not a roadmap item. This is something I'm not willing to troubleshoot and test.

## The gap this would close

Today, `homeconnect_local_hass` is internet-free for everything *except* one step: getting the appliance's profile file. This currently involves either the [Home Connect Profile Downloader](https://github.com/bruestel/homeconnect-profile-downloader) or this integration's own OAuth setup path (`hc_cloud_api.py`), both of which require logging into an account on the Home Connect cloud to pull that data. Once you have it, the appliance is controlled entirely over its local WebSocket, the cloud is never involved again, and you can disable the appliance's "Allow Cloud Connection" switch.

So the *only* remaining internet dependency is a one-time step during setup.

## The idea

A brand-new (or factory/network-reset) BSH appliance's very first WiFi/cloud account pairing is itself a network handshake with BSH's cloud, the appliance registers itself to a Home Connect account, and as part of that, its local encryption keys get established/reported.

If that handshake were pointed at a **local, fake cloud server** instead of BSH's real one, the same way `rethink` emulates LG's AWS backend for LG ThinQ appliances that have no local API at all, the appliance would complete pairing believing it registered to a real account, and the local keys could be captured directly from that handshake. No request would ever reach BSH's actual servers.

Combined with the fact that ongoing operation is already 100% local, this would mean **the entire appliance lifecycle, setup included, never touches BSH's cloud.** That's the appeal over the current OAuth-cloud-API approach: it makes the last "requires internet" optional instead of mandatory.

Since the web socket is the exact same regardless of whether it was setup with the fake or real cloud, this means that this integration can still cover both setup methods. It also benefits other Home Connect Local integrations like the ones for [Homey](https://homey.app/en-us/app/codes.lucasvdh.homeconnect/Home-Connect-(Local)/test/) or [OpenHab](https://www.openhab.org/addons/bindings/homeconnectdirect/).

## Why "Allow Cloud Connection" may still matter

>[!important]
> Whether this behavior will actually happen is unknown until its tested. Treat this like a theory.

Under this scheme, the appliance's own firmware believes it's legitimately registered to a Home Connect account (it doesn't know the account was fake). If its real cloud-connection toggle is left on afterward, it will periodically try to check in with BSH's *real* servers, which have no record of that registration. That mismatch is the whole scheme's exposure, BSH's servers seeing keys/credentials that don't match any real account is the one way this could get noticed or acted on. Turning "Allow Cloud Connection" off before the fake cloud is shutdown means the appliance never talks to the real cloud again, so there's nothing to notice. This may be a hard requirement of the design, not a nice-to-have.

## What's actually unknown (this is the real scope of the project)

None of the following has been reverse-engineered yet. This is not a "wire up rethink for BSH" task, it's a from-scratch protocol investigation, and the answer to the first point below could make the whole idea infeasible:

1. **TLS certificate pinning.** If the appliance validates BSH's real certificate chain during pairing and refuses to proceed against anything else, a fake local server can't complete the TLS handshake at all without getting the appliance to trust a custom root CA, which would require firmware-level access and defeats the point. This needs to be tested empirically (MITM proxy, e.g. `mitmproxy`, in front of a factory/network-reset appliance's first-time setup) before anything else here is worth building. If BSH pins certs strictly, this whole approach is likely dead on arrival.
2. **What hostname(s)/endpoints the appliance is hardcoded to contact** during initial pairing, and how it resolves them — needed to know what a local fake server needs to answer to, and how to redirect the appliance's traffic to it (local DNS interception on the network the appliance provisions over, same mechanism rethink uses for LG).
3. **The actual registration/pairing wire protocol**: request/response shapes, what triggers key generation vs. key upload, timing/retry behavior. This only comes from a live packet capture of a real pairing session.
4. **Failure modes.** If a fake response doesn't match what the appliance's firmware expects at any step, the appliance could error out, retry indefinitely, or get stuck in a half-provisioned state. Worth assuming a bricked pairing (recoverable by factory reset, but still) is a real possibility until proven otherwise, and testing on a spare/non-critical appliance if at all possible rather than a daily-driver one.

## Before making the software

Before writing any server code: capture a full packet trace (via a controlled AP running `mitmproxy` or even just `tcpdump`) of one already-owned appliance's factory/network-reset re-pairing process. That alone answers the certificate-pinning question, which determines whether the rest of this is worth attempting.

Also determine the WI-FI password, here's what I've confirmed so far
SSID: HomeConnect
Password: HomeConnect
I haven't confirmed if the password is this, but the SSID is confirmed. Seeing what the android app sends as the password to the appliance may be able to confirm it.

## Important appliances quirks.

A Home Connect Appliance is setup in a weird way. For some appliances like the Thermador T36IF905SP, pairing to WI-FI and connecting it to the app are two separate processes. But for most dishwashers like the Bosch SHE43DM5N it's one process. Some appliances like the Thermador PRG486WDH have support for WPS which may just connect it to wifi but not to the app. It's unknown how or if the appliance contacts the cloud in this phase, but what's known is that it doesn't open its web socket.

Future BSH Appliances will come with Matter which involves both wifi and bluetooth. The app may have to account for a bluetooth pairing process in the future.

For some reason a Home Connect Appliance can be registered to multiple accounts. Not sure how this would handle it.

## Potential network commands

>[!important]
> The WiFi change (the POST) is only confirmed on one appliance so far, and the reads on four. None of this was captured during an actual first-time setup. Treat everything here as a lead, not as documented behavior.

[@moerk-o](https://github.com/moerk-o) found that an already-paired appliance accepts WiFi credentials over its local WebSocket and moves to the new network by itself ([discussion #105](https://github.com/vemboy200/homeconnect_local_hass/discussions/105), [script](https://gist.github.com/moerk-o/5f3835fffee3ef1ad1e113676ef9bf73)). For this idea, that matters because the first step of the diagram below ("Phone shares home WiFi creds via appliance's own hotspot") has never been captured. This is the first known message that hands an appliance an SSID and password, so it's the most likely shape of that handoff.

### Response codes

The appliance answers every request with either data or a code. The ones seen so far:

| Code | Meaning |
| --- | --- |
| 200 | Accepted. For a GET the data comes back with it, for a POST the appliance applies it. |
| 400 | Bad request: the resource exists but the payload is wrong, e.g. a missing `interfaceID` or a wrong field name. Nothing changes on the appliance. |
| 404 | The resource doesn't exist on this appliance (usually a different service version). |

403 (not allowed), 405 (not writable) and 501 (not implemented) are also possible answers, but haven't come up in these tests.

### What was tried

All of these go over the existing, authenticated WebSocket, after the handshake:

| Resource | Action | Result |
| --- | --- | --- |
| `/ni/info` | GET | 200. The network the appliance is currently on: SSID, RSSI, status, MAC, IPv4/IPv6. |
| `/ni/config` | GET with payload `[{"interfaceID": 0}]` | 200. Returns `interfaceID`, `ssid`, `automaticIPv4`, `automaticIPv6`. Never returns the password. |
| `/ni/config` | GET without a payload | 400. |
| `/ni/config` | POST | 200. Changes the WiFi network (see below). |
| `/ci/wifiNetworks` | GET | 200. A WiFi scan: SSID and RSSI of every network the appliance can see. |
| `/ci/wifiSetting` | GET | 404. The [protocol notes](https://github.com/chris-mc1/homeconnect_websocket/blob/main/doc/Home_Connect_Protocol.md) describe it under `ci` version 1 (SSID and automatic IP flags, like `/ni/config`). |
| `/ci/networkDetails` | GET | 404. Also `ci` version 1 in the protocol notes (current IPv4/IPv6 addresses, like part of `/ni/info`). |
| `/ci/wifiSetting2` | GET | 404. Only known by name, from the resource lists in [hcpy](https://github.com/osresearch/hcpy/blob/main/HCDevice.py) and the openHAB binding. No one has documented what it returns. |
| `/ci/networkDetails2` | GET | 404. Same as `/ci/wifiSetting2`: a name from those lists, contents unknown. |

The four `/ci/` resources look like an older version of what `/ni/` does now, which fits every tested appliance speaking `ci` version 2 and `ni` version 1.

The write:

```json
// POST /ni/config
[
  {
    "interfaceID": 0,
    "ssid": "NewNetwork",
    "passphrase": "…",
    "automaticIPv4": true,
    "automaticIPv6": true
  }
]
```

The password field is `passphrase`. `psk` is rejected with 400, and so is every other name the script tried.

### Appliances tested

moerk-o ran the whole script on the Siemens oven. The three Thermadors only got the script's `--read` mode (every GET above, no POST), and they answered exactly like the Siemens:

| Appliance | Services | `/ni/info` | `/ni/config` GET | `/ci/wifiSetting` | `/ci/wifiSetting2` | `/ci/networkDetails` | `/ci/networkDetails2` | `/ci/wifiNetworks` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Siemens HB876G8B6/75 oven (fw 2.11.6.13174) | `ro` 1, `ei` 2, `ci` 2, `ni` 1 | 200 | 200 with payload, 400 without | 404 | 404 | 404 | 404 | 200 |
| Thermador PRG486WDH range | `ro` 1, `ei` 2, `ci` 2, `ni` 1 | 200 | 200 with payload, 400 without | 404 | 404 | 404 | 404 | 200 |
| Thermador T36IF905SP freezer | `ro` 1, `ei` 2, `ci` 2, `ni` 1 | 200 | 200 with payload, 400 without | 404 | 404 | 404 | 404 | 200 |
| Thermador DWHD660WFP dishwasher (2020) | `ro` 1, `ei` 2, `ci` 2, `ni` 1 | 200 | 200 with payload, 400 without | 404 | 404 | 404 | 404 | 200 |

Two brands and three appliance types exposing the same resources the same way points at a shared platform rather than one oven's firmware. Whether the Thermadors accept the POST is still unconfirmed.

### What this means for pairing

- **A likely payload for the WiFi handoff.** A setup tool would need to hand the appliance the home network's SSID and password over the hotspot. `POST /ni/config` with `ssid` + `passphrase` is a strong guess for that message. It's only a guess until the app's hotspot traffic is captured: first-time setup might use a different resource or field names.
- **Showing networks instead of typing them.** `/ci/wifiNetworks` returns the networks the appliance itself can see. A setup tool could offer those instead of asking for an SSID, which also rules out picking a network the appliance can't use. Only 2.4 GHz networks showed up in the tests, which fits these appliances being 2.4 GHz only (not proven by such a small scan).
- **A wrong password during setup is a known dead end.** In [this video](https://youtu.be/hpe7zislhqQ?t=1305) (21:45-23:08), a wrong WiFi password on a refrigerator leaves the official app's setup stuck, and "you do not get to retry the password": the app's retry button tries again without asking for it, reinstalling the app doesn't help, and the only way out is resetting the appliance's network settings from its own menu. Since reinstalling the app changed nothing, the wrong password seems to be stored on the appliance, which keeps retrying it. A setup tool should make the user confirm the password before sending it, and point to the appliance's menu reset as the way back.
- **Which key does the hotspot connection use?** Every request above needs an already-authenticated WebSocket, which needs the appliance's encryption key. A factory-reset appliance on its "HomeConnect" hotspot hasn't been registered to an account yet. Either the hotspot step uses a different channel or a default key, or the appliance already has its key before cloud registration. If it's the second, that changes a lot here: the key would come from the appliance, not from the cloud handshake. Capturing the hotspot step answers this.
- **More resource names to watch for in a capture.** The same hcpy list also names `/ci/register`, `/ci/deregister`, `/ci/registeredDevices`, `/ci/pairableDevices`, `/ci/delregistration` and a whole `ce` group (`/ce/serverDeviceType`, `/ce/serverCredential`, `/ce/clientCredential`, `/ce/hubInformation`, `/ce/hubConnected`, `/ce/status`). By their names, these sound like registration and credential exchange, which is exactly the part of pairing this idea needs to fake. None of them has been tested or documented.

<details>
<summary>Changing the network after setup</summary>

This part isn't about first-time pairing, but it's what was actually tested.

- After the 200, the appliance closes the WebSocket, leaves its current network and joins the new one. It never goes into a pairing mode: it stays on its network the whole time, receives the new network's details over the local connection, and switches on its own. About 30 seconds later it was reachable on the new network with a new IP, and this integration found it again through mDNS and updated the host in the config entry by itself.
- Writing the current network back (same SSID and password) is a safe way to test whether an appliance accepts the write at all: it drops briefly and rejoins the same network.
- According to the protocol notes, `/ni/config` also has `manualIPv4` / `manualIPv6` blocks (address, prefix, gateway, DNS) when the automatic flags are false, so static IPs are probably set the same way. Not tested.
- The app's "Extended network settings" refuse to work unless the phone is on the same network as the appliance ("Network change unavailable"), which fits a local-only command like this. Probably what the app uses, but its traffic hasn't been captured.
- **Wrong password after setup: unknown.** The appliance might fall back to the network that was working, or it might be left with no network until it's reset from its menu, like the setup case above. That fridge had no earlier working network to go back to, so the video doesn't answer this.
- **Not an integration feature.** Changing the WiFi network falls in the same category as the commands this integration deliberately leaves out (factory reset, network reset, WiFi deactivation): a mistake can leave the appliance unreachable. It's also a reminder of why the Full profile export (which contains the encryption key) stays gated: anyone with that key can move the appliance off your network over the local connection.

</details>

### Open questions

- **Appliances with `ci` 3 or an `iz` service.** Every appliance tested so far is `ci` 2 without `iz`, including the 2020 Thermador dishwasher. Newer ones (some dishwashers report `ci` 3 and `iz`) may expose this differently or not at all. The script's read-only mode is the safe way to check, since it changes nothing on the appliance.
- **The hotspot key and the actual first-time handoff.** See "What this means for pairing". Only a capture of a real first-time setup answers these.

## How the software would work

During the pairing process the app would be both the cloud and phone in parallel.

- Phone = App emulating the phone during the process
- Cloud = App emulating the cloud during the process

```
Phone --(shares home WiFi creds via appliance's own hotspot)--> Appliance
                                                                    |
                                                                    v
                                                        Appliance joins home WAP
                                                                    |
                                                                    v
                                                    Appliance <==TLS==> Fake Cloud
                                                     (registers, reports/negotiates
                                                            local keys)
                                                                    |
                                                                    v
                                                  Fake Cloud has everything needed
                                                    for the appliance's profile
                                                                    |
                                                                    v
                                                  Profile file lands on the user's
                                                          computer
                                                                    |
                                                                    v
                                             Imported into homeconnect_local_hass
                                                                    |
                                          +-------------------------+-------------------------+
                                          |                                                   |
                                          v                                                   v
                                4.1 Phone/HA side                                    4.2 Cloud side
                        Phone/HA -> appliance's local WS                      Fake Cloud (still connected)
                         using keys from the profile                           sends disable-cloud itself
                    (what the integration can do right now)                    (harder: payload unknown)
                                          |                                                   |
                                          +-------------------------+-------------------------+
                                                                    |
                                                                    v
                                                    Appliance's cloud connection off
                                                                    |
                                                                    v
                                                       100% local from here on
```

### Some stuff to point out

- There has to be a fake account.
- It's unknown if the appliance sends the full profile file to cloud or data that the cloud then refactors into a profile file.
- The good news is this setup **does not** override the appliance's firmware, so once the software is ready for the public it's not super risky.

### Another idea

After the software is developed and thoroughly tested, to simplify setup, the app could also go in a pairing mode. During this pairing mode Home Assistant can connect to the computer which has the profile file, and take it and then connect to the appliance.

## Prior work

- [rethink](https://github.com/anszom/rethink): the LG ThinQ equivalent. Their situation is actually harder than BSH's: LG appliances have no local API at all, so rethink has to keep a fake cloud running permanently to handle ongoing control. Here, the fake cloud would only ever need to run for the few minutes of initial pairing, everything after that is already native and local.
