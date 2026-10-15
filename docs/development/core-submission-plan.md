# Core submission plan

This is the plan for getting Home Connect Local into Home Assistant core. It has four phases: what has to be done in the library before the first PR, the initial submission itself, porting everything else afterwards, and what happens to this repository once everything is in core.

Nothing here is scheduled yet, so treat this as the order of work, not a timeline. Phase 1 is nearly done; see [Status](#status) for what's left.

> [!NOTE]
> Home Assistant's own rules this plan follows: the [review process](https://developers.home-assistant.io/docs/review-process/), the [integration quality scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/) and the [documentation standards](https://developers.home-assistant.io/docs/documenting/standards/). Where this plan and those pages disagree, those pages win.

## Current size

Entity descriptions in `entity_descriptions/`, counted on `dev` on 2026-10-14 (after #196). This number changes with almost every feature PR, so recount before relying on it.

| Platform | Descriptions |
| --- | --- |
| `sensor` | 75 |
| `binary_sensor` | 72 |
| `switch` | 73 |
| `select` | 102 |
| `number` | 33 |
| `button` | 14 |
| `light` | 7 |
| `fan` | 1 |
| `update` | 2 |
| **Total** | **379** |

- **Descriptions** is every `HC*EntityDescription(...)` in the code. Each key is described once (#196): a feature with an old and a new name (for example `Refrigeration.FridgeFreezer.Setting.EcoMode` and `Refrigeration.Common.Setting.EcoMode`) is one description with `alternate_entities`, and a light with or without brightness or color is one description too. Celsius/Fahrenheit pairs have a key each, so they count twice, but an appliance that reports both gets one entity, in Home Assistant's unit (#194).
- It isn't the number of entities one appliance gets. An appliance only gets the descriptions it reports, and a few descriptions (oven cavities, hob zones) create one entity per cavity or zone.

<details>
<summary>Recount</summary>

Run from the repository root:

```python
import glob
import re

files = [
    f
    for f in glob.glob("custom_components/homeconnect_ws/entity_descriptions/*.py")
    if not f.endswith(("__init__.py", "descriptions_definitions.py"))
]
for kind in ["Sensor", "BinarySensor", "Switch", "Select", "Number", "Button", "Light", "Fan", "Update"]:
    total, keys, unnamed = 0, set(), 0
    for f in files:
        src = open(f).read()
        for match in re.finditer(rf"HC{kind}EntityDescription\(", src):
            total += 1
            key = re.match(r'\s*key="([^"]+)"', src[match.end():])
            if key:
                keys.add(key.group(1))
            else:
                unnamed += 1
    print(kind, total, len(keys) + unnamed)
```

</details>

## Phase 1: before the submission (the library)

### Status

As of 2026-10-12, with home-disconnect 2.0.0b3 and Home Connect Local 2.0.0b0 (b1 drafted):

| Step | State |
| --- | --- |
| [1. License the library](#1-license-the-library-blocker) | **Done.** home-disconnect 2.0 is a new MIT-licensed library ([repository](https://github.com/vemboy200/home-disconnect)), with `PROVENANCE.md` and `THIRD_PARTY_NOTICES.md` (hcpy, code moved from this integration) and its own test suite. No code from `homeconnect_websocket` or home-disconnect 1.x. Home Connect Local 2.0.0b0 runs on it (#122). |
| [2. Move protocol logic into the library](#2-move-protocol-logic-into-the-library) | **Done except the feature-name constants.** See the table below. |
| [3. Library release pipeline](#3-library-release-pipeline) | **Done except a stable release.** CI (lint, tests on 3.13 and 3.14, mypy, build), PyPI Trusted Publishing from GitHub releases (`publish.yml`), MIT license metadata, Renovate only. Releases so far are 2.0.0b0 to 2.0.0b3. |

What's left before Phase 2:

- **Feature-name constants.** The entity descriptions still name about 440 features as strings (`"BSH.Common.Status.DoorState"`). Not started.
- **A stable home-disconnect 2.0.0** for core to pin. It waits on the Home Connect Local 2.0 betas being tested on real appliances (hoods, washers and dryers, program starts and delays, setup), and on the heartbeat change (home-disconnect #20).
- **The entity description layout** from [Decisions to make first](#decisions-to-make-first) (descriptions per platform file). Planned for v2.0.0's entity cleanup, not done yet.

### 1. License the library (blocker)

Core only accepts dependencies with an [OSI-approved license](https://opensource.org/licenses). `home-disconnect` is a fork of chris-mc1's [homeconnect_websocket](https://github.com/chris-mc1/homeconnect_websocket), which has no license at all ([upstream issue #69](https://github.com/chris-mc1/homeconnect_websocket/issues/69), open and unanswered). Without a license that code is all rights reserved, and only its author can license it. About 90% of the library's source is still his code, so the fork can't add a license by itself.

The plan is **home-disconnect v2.0.0: a reimplementation that can carry a license** (MIT or Apache-2.0):

- Write new code from the protocol, not by editing or translating the upstream files. Protocol facts (message format, resources, the AES and TLS-PSK schemes, handshake order) aren't copyrightable; the upstream code and its protocol document are.
- [hcpy](https://github.com/osresearch/hcpy) is MIT and covers the crypto and websocket protocol, so it can be used with attribution. openHAB's Home Connect Direct binding is EPL-2.0: reference only, don't copy.
- Write a new test suite too (the current one is also mostly upstream code).
- Document the provenance in the library's repository: what came from hcpy, what from protocol observation and what was moved from this integration.
- Keep the public API close to 1.x so this integration's migration stays small.

If chris-mc1 licenses upstream before v2 lands, the rewrite becomes optional.

### 2. Move protocol logic into the library

Core requires code that talks to a device or service to live in the library, not the integration. v2.0.0 of both repositories moves these out of the integration:

| In the integration today | Moves to | Status |
| --- | --- | --- |
| Hand-built messages: start with Finish-in (`__init__.py`), `fan.py` and `light.py` writes | Library methods (start a program with options, batch value writes) | Done: `start_program(delay=)`, `set_finish_in()`, the hood fan helpers and `set_ambient_light()` (#122, #160, #163, #164). The integration sends no messages of its own. |
| Program and option rules in `helpers.py`: locking, `ensure_writable`, full vs known option sets, unplugged probes | Library `select_program()` / `start_program()` that own these rules | Done: option sets, unplugged probes, read-only options per program (home-disconnect #25) and the remote start check (#162) are in the library, and locking is its `Entity.locked`. `ensure_writable` stays only to turn a lock into Home Assistant's error. |
| `hc_cloud_api.py` and `hc_legacy_oauth.py` (account sign-in and profile fetch) | One library module, something like `home_disconnect.account` (drop the "legacy" name, it's the app's own sign-in) | Done: `home_disconnect.account` (#122). |
| Profile ZIP reading and writing (`config_flow.py`, `export_profile.py`, `hc_cloud_api.py`) | One library profile loader and writer (the simulator can use it too) | Done: `home_disconnect.profile_files` (#122). |
| Clock sync timestamp format | Something like `appliance.set_datetime()` | Done: `appliance.set_datetime()` (#122). |
| Feature names written as strings in the entity descriptions (`"BSH.Common.Status.DoorState"`, about 440 of them) | Library constants the descriptions reference, the way core's `home_connect` uses `aiohomeconnect`'s `StatusKey` | Not started. |
| Finding oven cavities, hob zones and favorites in the profile (`get_groups_from_regex` and the regexes in `cooking.py` and `common.py`) | A library call that lists them, for example an oven's cavity IDs | Done: `group_ids()` (#122). |

Entities, entity descriptions, the config flow UI, storage paths, the error decorator and translations stay in the integration. The descriptions are Home Assistant code (they extend HA's `*EntityDescription` classes and use its device classes and units), and a library can't depend on Home Assistant. Core's `roborock` is the pattern: its descriptions live in the integration and point at the library for the value (`data.status.battery`), the options (`WaterLevelMapping`) and the command (`api.set_water_level`).

The integration is MIT (© chris_mc1), so code moved from here into the library is licensed. Keep the MIT notice and credit him.

### 3. Library release pipeline

Before the first review, the library needs:

- A real CI/CD pipeline: lint, tests, type checking, and publishing to PyPI with [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) from tagged GitHub releases. Reviewers check this on new dependencies.
- The license file and PyPI license metadata.
- A stable (non-pre-release) version for core to pin.
- One dependency bot (keep Renovate, drop Dependabot).

## Phase 2: the initial submission

The first core PR is as small as core allows: **one platform (`sensor`), the config flow and nothing else.**

### Decisions to make first

| Decision | Recommendation | Why |
| --- | --- | --- |
| Setup path | Home Connect sign-in only in the initial PR; the profile ZIP upload can follow later (Phase 3) | Keeps setup inside Home Assistant with no third-party desktop tool. Core `simplisafe` also signs in with its vendor app's client and a pasted redirect. |
| Initial platform | `sensor` | Read-only, so none of the program/option write rules have to be reviewed in the first PR. Status sensors (operation state, active program, remaining time) exist on nearly every appliance type. |
| Domain | Keep `homeconnect_ws` if reviewers accept it, otherwise pick a new one early | Same domain means custom users can switch without re-adding appliances (see [Phase 4](#phase-4-after-everything-is-ported)). A new domain means everyone re-adds their appliances. `ws` is an implementation detail, so expect reviewers to question it. If it has to change, `home_connect_local` follows core's `powerfox` / `powerfox_local` naming ("Powerfox Cloud" and "Powerfox Local", grouped under one Powerfox brand). |
| Stored profiles | Core only reads entries that store the profile XML (`description_xml` and `feature_mapping_xml`), the format 2.0 writes for new and reconfigured appliances. The conversions from older formats stay out of the initial PR. If the domain stays `homeconnect_ws`, the last custom release before people switch rewrites every entry to XML, so core never sees an older one. Adding the conversions to core in a later PR is the fallback | 2.0 still loads entries saved by 1.x (the parsed profile in the entry) and by upstream chris-mc1 (the parsed profile in separate files), converting them each time without writing back, so going back to 1.9 keeps working. Carrying those conversions into core would mean core migrating a custom integration's storage formats, which isn't essential for the first platform and which reviewers would likely question. With a new domain everyone re-adds their appliances, so no conversion is needed at all |
| Brand | Add the domain to core's existing Bosch brand (`homeassistant/brands/bosch.json`) | Core lists `home_connect` under Bosch, next to `bosch_alarm` and `bosch_shc`, so the local integration belongs in the same brand. There's no Siemens, Thermador or other BSH brand file to add it to. |
| Entity description layout | Each platform's descriptions in its own platform file (`sensor.py`, `binary_sensor.py`, ...), with its description class. Switch the custom integration over in v2.0.0's entity cleanup (b1), so each core PR is a copy of one file. Generators that build descriptions for several platforms at once (e.g. `generate_oven_status`, which makes sensors and binary sensors per cavity) get split per platform too. If a platform gets too big for one file, turn it into a package split by appliance type (`sensor/cooking.py`, `sensor/laundry_care.py`, ...) | `entity_descriptions/` splits by appliance type, and each file covers every platform. Nothing in core is laid out that way: on core `dev` (2026-09-16) only 30 of 1,525 integrations have a Python subfolder at all, and the cloud `home_connect` integration keeps each platform's descriptions in that platform's file. Core's precedent for too many descriptions is splitting one platform by device type: `growatt_server/sensor/` (`inverter.py`, `mix.py`, `storage.py`, ... plus a shared `sensor_entity_description.py`) and `overkiz/climate/`. The descriptions themselves stay in the integration either way (they're built on HA's classes); only the feature names move to the library. |

### What's in it

- Config flow: the Home Connect sign-in, appliance selection and connection test. Keep the test-before-setup split for washers and dryers, which cut their WiFi when off (see the `quality_scale.yaml` comment).
- The coordinator and connection handling (push updates, heartbeat, reconnect with backoff).
- Zeroconf discovery (`_homeconnect._tcp.local.`). Each appliance is its own config entry, so a discovered appliance that's already set up is ignored. The cloud `home_connect` integration listens for the same service type (and for DHCP), so on a fresh install both integrations can show a discovered card for the same appliance. That's accepted in core: `powerfox` (cloud) and `powerfox_local` both discover the same poweropti devices with the same zeroconf matcher, and both mark `discovery` as done. It's still worth saying in the PR description. Removing discovery from the cloud integration is its code owners' decision, not part of this plan.
- `sensor` entities, without the diagnostic ones. The custom integration has 75 sensor descriptions, and 9 of them are diagnostic: WiFi signal strength, IPv4 and IPv6 address, water and energy forecast, started and completed program counts, the program end trigger and the dishwasher's machine care reminder. Leaving them out also leaves out the WiFi signal sensor, the only entity that polls (`/ni/info`), so the first PR is push-only.
  - That still leaves 66, spread over every appliance type. The plan is to accept that: entity descriptions are declarative data, so most of the review is the entity classes and the coordinator, not the list.
  - Each feature gets one entity, so a sensor-only first PR leaves out what's a control or a binary sensor in the custom integration. Power state is always a switch or a select (#193), so it comes with those platforms. The door is a sensor only when it can also be locked or ajar (#194); a door that's only open or closed is a binary sensor, which comes with `binary_sensor`.
  - If reviewers say 66 is too many, cut by file, not by appliance: keep the 14 shared sensors in `common.py` (operation state, door, active program, remaining, elapsed and estimated time, progress, start in, finish in, flex start, energy and water consumed, and the last program's energy and water) plus the 3 in `dishcare.py` (rinse aid, salt, program phase), 17 in total. Every appliance type reports the shared ones, so no appliance loses support, it just gets fewer sensors at first. Dishwashers keep their own because they're the appliance BSH pushes Home Connect hardest on. The other appliance-specific sensors then come back one family per PR (cooking, laundry, refrigeration, coffee makers). Cutting out whole appliance types isn't needed.
- Tests with full config flow coverage, and tests for the sensor platform.
- The quality scale as far as the initial PR allows. Everything the custom integration already meets stays `done`, except the three rules for features left out of the initial PR: `diagnostics`, `reauthentication-flow` and `reconfiguration-flow` are `todo`. `dynamic-devices` and `stale-devices` stay exempt (one appliance per config entry). Rules about actions (`action-setup`, `docs-actions`) become exempt while there are no integration actions, and the rest are checked against the `sensor` platform alone. Because `reauthentication-flow` is a Silver rule, the manifest still declares **Bronze** at first, even though nearly every Silver, Gold and Platinum rule is already done.
- The documentation PR on home-assistant.io, opened at the same time.

### What's left out on purpose

| Left out | Why |
| --- | --- |
| Every other platform | Initial submissions are one platform. |
| Diagnostics | Not needed for the platform to work. |
| Reauthentication and reconfiguration flows | Not needed for the platform to work. |
| Options flow (Full profile export) | Not needed for the platform to work. |
| The `start_program`, `set_start_in` and `set_finish_in` actions | No custom actions in an initial submission. |
| Loading entries saved by 1.x or upstream chris-mc1 (`legacy.py` and the separate-files conversion) | Not needed for the platform to work; see Stored profiles above. |

### Things to strip from the core copy

- The dev-only "setup from diagnostics dump" path: `CONF_DEV_SETUP_FROM_DUMP`, `CONF_DEV_OVERRIDE_HOST`, `CONF_DEV_OVERRIDE_PSK`, `CONFIG_SCHEMA`, the `HCConfig` / `hass.data` wiring, `process_json_file`, the `setup_from_dump` branch and the placeholder-host fallback that only exists for dump entries.
- The profile ZIP upload step and the `file_upload` after-dependency (if the sign-in is the chosen setup path). It can come back as a follow-up, see Phase 3.
- Every translation file except English: core keeps `strings.json` and translations come from Lokalise. The German requirement in this repository doesn't carry over.
- Anything written defensively for states the data model already rules out. Reviewers ask "why can this be None?", and if the honest answer is "it can't", the code goes.
- Extra state attributes on the initial PR's sensors: `Is Estimated` on the remaining program time, `Auto Counting` on the oven's cooking times and `Type` on the hob zones. Core discourages new state attributes, so each one either becomes its own entity or is dropped (see [State attributes](#state-attributes-and-the-readonly-attribute)).
- The grouped event sensors (`HCEventSensor`, e.g. the coffee maker's Descaling sensor). They read events the same way the event binary sensors do (see [Event sensors](#event-sensors-present-and-confirmed)), so they come over with the `binary_sensor` PR and that question is explained once.

### Pre-flight

- Run the integration against core's dev branch with core's own linters and hassfest, not only this repository's CI.
- Check every pattern (config entry data keys, selectors, quality scale exemptions) against an existing core integration instead of guessing.
- Give the docs page its own pass against the documentation standards. The linters don't catch broken entity references or discouraged terms.

### Timing

- Base the PR on the latest core `dev` and keep it rebased. A rebase can break CI through dependency drift (ruff, mypy) even when this code didn't change; that's usually a quick mechanical fix.
- Reviewers don't review on weekends.
- New integrations effectively have to be merged before a release's b0 beta to ship in that release.

## Phase 3: porting the rest

After the initial PR is merged, everything else comes over as small follow-up PRs, one thing per PR. Each PR is tested on real appliances through a custom build of the core integration first.

Expect 15-23 core PRs including the initial one (the range depends on whether the sensor fallback is used, whether `select` and `light`/`fan` need splitting, and whether the full profile export and profile upload are accepted). On top of that come a matching home-assistant.io docs PR for most of them, a standalone PR for each library bump, and the brand PRs. The target is **3-5 months from the initial PR's merge**, based on the PowerShades submission. That doesn't include the library rewrite (Phase 1) or the initial review itself, which is usually the slowest part. Hitting it means keeping independent PRs open in parallel (for example diagnostics, the brand PRs and `update`) instead of waiting for each merge before opening the next.

### Porting progress

Start tracking this once the initial PR is merged, and update it with every follow-up PR. **In core** is how many of the custom integration's descriptions the core integration has; the bar is that as a share of the total.

| Platform | Custom | In core | Progress |
| --- | --- | --- | --- |
| `sensor` | 73 | 0 | `░░░░░░░░░░` 0% |
| `binary_sensor` | 74 | 0 | `░░░░░░░░░░` 0% |
| `switch` | 83 | 0 | `░░░░░░░░░░` 0% |
| `select` | 97 | 0 | `░░░░░░░░░░` 0% |
| `number` | 34 | 0 | `░░░░░░░░░░` 0% |
| `button` | 12 | 0 | `░░░░░░░░░░` 0% |
| `light` | 13 | 0 | `░░░░░░░░░░` 0% |
| `fan` | 1 | 0 | `░░░░░░░░░░` 0% |
| `update` | 2 | 0 | `░░░░░░░░░░` 0% |
| **Total** | **389** | **0** | `░░░░░░░░░░` **0%** |

Each `█` is 10%. Take the count from [Current size](#current-size) at the time, since the custom integration keeps changing while the port runs.

Suggested order (description counts are how many entity descriptions each platform has; one appliance only gets the ones it reports):

1. **Diagnostics** (the `diagnostics` Gold rule).
2. **The sensors left out of the initial PR:** the 9 diagnostic sensors, and if the 17-sensor fallback was used, the cooking, laundry, refrigeration and coffee maker sensors, one family per PR.
3. **`binary_sensor`** (72 descriptions), split in two:
   - shared, dishwasher and laundry (44): remote start allowed, door, dishwasher and laundry problem events;
   - refrigeration, cooking and coffee makers (28): mostly the fridge and freezer door and alarm sensors.
4. **`select`** (102 descriptions, each a separate entity; the dropdown values aren't counted): program selection and options, including locked (read-only) entities and filtering unavailable programs.
5. **`switch`** (73 descriptions), split in two:
   - shared, dishwasher and laundry (46);
   - cooking, refrigeration and coffee makers (27).
6. **`number`** (33): settings and options.
7. **`button`** (14): Start, Stop, Pause and the rest. After `select`, since starting needs a selected program.
8. **`light`** (7) and **`fan`** (1): hood lighting and venting.
9. **`update`** (2): software updates.
10. **Reconfiguration flow, then reauthentication flow last.** Reconfiguration covers what changes in normal use (the appliance's address, or a new profile after a firmware update adds options). Reauthentication is only needed when the local key changes, which only happens when the appliance is unpaired and paired again, so it's the least urgent. Reauthentication is also the only Silver rule left, so the manifest stays at Bronze until it lands and then goes straight to Platinum: diagnostics and reconfiguration are the only Gold rules left and will already be in, and the Platinum rules are already done.
11. **Start with delay:** replace the `start_program` / `set_start_in` / `set_finish_in` actions with entities if possible (for example a Start-in / Finish-in entity), since core prefers entities over integration actions. Keep an action only if an entity can't express it.
12. **Full profile export**, if core allows an integration to write a file containing the local key (not confirmed yet). The safe export needs nothing extra: it's Home Assistant's own Download Diagnostics. Two ways to offer the full one:
   - As it works now: a "Configure" (options flow) step that writes the ZIP to the config directory after an explicit confirmation.
   - As an integration action that writes the file. Core's `camera.snapshot` is a precedent for an action writing a file, limited to the directories allowed by `allowlist_external_dirs`. This brings back `action-setup` and `docs-actions`, so they'd go from exempt to done.
13. **Profile ZIP upload as a second setup path**, if reviewers accept two ways to set up. It's the fallback for anyone who can't or doesn't want to use the Home Connect sign-in, and the way to set up if BSH ever blocks the sign-in client. Core `knx` accepts an uploaded keyring file as precedent. The reconfiguration flow's "update profile file" option uses the same upload, so if this is rejected, reconfiguration only offers a profile refresh through the sign-in.
14. **The other BSH brands (nice to have).** Core has 8 virtual integrations that point people searching for another BSH brand to the cloud `home_connect` integration: Balay, Constructa, Gaggenau, Neff, Pitsos, Profilo, Siemens and Thermador. Each is a manifest with `"integration_type": "virtual"` and `"supported_by": "home_connect"`, and `supported_by` takes a single domain, so they can't also point to this integration. Someone searching "Thermador" or "Siemens" would only find the cloud integration. Options, to settle with reviewers:
   - Turn each of them into a brand (`homeassistant/brands/siemens.json` and so on) that lists both `home_connect` and this integration, the same way `bosch.json` lists several. This is a change to how the cloud integration is presented, so its code owners should agree.
   - Leave them as they are and rely on the Bosch brand plus the docs mentioning every brand.

   This has to come after the initial PR is merged, because hassfest checks that referenced domains exist. It doesn't block anything else, so it's left for last.

Features that are on the custom integration's own roadmap (for example the per-appliance option-value calibration from [discussion #104](https://github.com/vemboy200/homeconnect_local_hass/discussions/104)) go into whichever side is current at the time. Where core's cloud `home_connect` integration has the same limitation, fixing it isn't a condition for the port.

Expect issues from people who remove the custom integration and switch to core before the port is finished: missing entities, and if the domain stayed `homeconnect_ws`, entries that don't load because the custom integration created them with a newer config entry version than core has. Handle those as they come in.

While porting, the custom integration stays the place to try new things. Anything added here before it's ported gets ported in the same way.

## Phase 4: after everything is ported

- **Deprecate the custom integration.** Once core has feature parity, stop adding features here and put a notice at the top of the README pointing to the core integration.
- **Migration guide.** If the domain stayed `homeconnect_ws`, removing the custom integration from HACS and restarting keeps every config entry, device and entity, because the core integration reads the same entries and unique IDs. This needs the custom release that rewrites every entry to XML first (see Stored profiles under [Decisions to make first](#decisions-to-make-first)); anyone who skips it has entries core can't load. Document the exact steps and test them on a real install first. If the domain changed, the guide is "remove and re-add each appliance".
- **Issues and discussions.** Point new reports to the core issue tracker. Keep this repository's issues open until the existing ones are resolved or moved.
- **Docs.** The user-facing pages in `docs/integration/` move into the home-assistant.io integration page. Everything in `docs/development/` except this plan moves to the library (`home-disconnect`), since that's where protocol work happens from then on. So do the parts of the user docs that home-assistant.io won't take: the reverse-engineering guide under "Requesting a New Feature" (matching debug log UIDs to profile features), and protocol detail in Known Limitations such as WebSocket close codes and which errors mean a websocket shutdown. The integration page keeps a short version of each and links to the library for the rest. Update the links to the moved pages in the README and the PR template.
- **The library** stays maintained as a standalone project, since core depends on it. It becomes the place for protocol work.
- **The simulator** stays a development tool. It isn't part of the core submission.
- **Archiving** this repository is optional. Keeping it around for pre-releases of new features is fine, as long as the README makes clear core is the main version.

### Features for after the port

New features that wait until core has everything and don't belong in the initial submission:

- **Program and option names per brand** (upstream chris-mc1/homeconnect_local_hass#94). Names come from BSH's keys, but brands market the same feature under different names: the dishwasher option Bosch calls CrystalDry is StarDry on newer Thermadors. Give an entity a brand-specific `translation_key` (e.g. `program_thermador`) when that brand has names contributed, and keep today's generic names for every other brand. It stays in the translation files, so hassfest validates it and each brand's names can be translated. Names come from owners picking each program and noting what the appliance shows, so coverage grows with contributions. A brand can still name a key differently by region (joe-sydney's SMU6HCS01A is an Australian Bosch), so a region or model override on top of the brand names may be needed later. Before building it, check whether any core integration chooses translation keys per brand or model, and whether BSH's cloud profile archive carries the app's display names, which would give the real names without contributions.

### Relationship with the cloud integration

Home Connect Local and the cloud `home_connect` integration will coexist in core. Home Assistant doesn't remove an integration because a newer one does more; removals happen when a service or library stops working or nobody maintains it. The cloud integration is actively maintained and uses BSH's official API, so plan around both staying.

Each has reasons to pick it:

| Pick Home Connect Local for | Pick the cloud integration for |
| --- | --- |
| More entities than the official API exposes | Setup with the official sign-in, no local key involved |
| Faster responses (no round trip through BSH's servers) | Support from BSH: firmware updates won't break it, while the local protocol is reverse-engineered |
| Keeps working without internet and with the cloud connection turned off | Setups where Home Assistant can't reach the appliance at all, such as a firewall blocking the appliance's network or Home Assistant running at a different site. A missing mDNS route alone isn't one of them, since Home Connect Local can connect by IP address |

The docs for both integrations should explain this so people can choose.

## Design calls reviewers will ask about

Places where the integration deliberately doesn't show the appliance's raw data one-to-one. Each needs a short explanation in the PR that brings it to core. The rule for all of them: show what the appliance reports, only correct data that's shown to be wrong, and don't invent states. The custom integration follows the same rule, so nothing here is custom-only.

### Event sensors: Present and Confirmed

Appliances report events (salt low, door alarm, descaling due and so on) as `Present`, `Confirmed` or `Off`. The integration shows them as binary sensors that are on for both `Present` and `Confirmed`, and off for `Off`. That's 63 of the 81 binary sensor descriptions (counted on `beta` on 2026-10-04), plus the grouped event sensors on the `sensor` platform, which treat both as active too.

**Decision: keep them binary.** The official [Home Connect API documentation](https://api-docs.home-connect.com/events#event-present-state-enumeration) defines `Confirmed` as "The event has been confirmed by the user": acknowledged on the appliance, but not cleared. Only `Off` means the event is over (the freezer door alarm stays active while the door is still open, even after the beep is silenced). So on/off follows the actual condition, and acknowledging a message on the display doesn't make Home Assistant report the problem as solved. Appliances also rarely report `Confirmed` at all (not yet checked on the local API).

Text for the `binary_sensor` PR:

> **Event mapping:** Home Connect reports events as `Present`, `Confirmed` or `Off`. Per the [Home Connect API documentation](https://api-docs.home-connect.com/events#event-present-state-enumeration), `Confirmed` means "the event has been confirmed by the user", i.e. acknowledged on the appliance, while the event itself is still active; only `Off` means it has cleared (for example, the freezer door alarm stays active while the door is still open, even after the beep is silenced). These binary sensors are therefore on for both `Present` and `Confirmed`, and off only for `Off`. Acknowledging a message on the appliance's display shouldn't make Home Assistant report the problem as solved, and this keeps automations simple: one on/off state that tracks the actual condition.

Rejected alternatives:

- **Enum sensors with all three states** (what the cloud `home_connect` integration does). Turns the biggest platform into enum sensors for a difference most events don't need.
- **Both a binary and an enum sensor per event.** Core doesn't want two entities for the same data.
- **A `confirmed` state attribute.** Core discourages new state attributes, so don't offer it in the PR.

If a reviewer asks how to tell `Confirmed` from `Present`, answer then: a separate enum sensor, disabled by default, for only the events where it matters (the door alarms are the likely ones). Not an attribute.

### State attributes and the `readonly` attribute

Core discourages extra state attributes in new code: they're stored with every state change, are awkward to use in automations, and reviewers usually ask for a separate entity instead or for the attribute to be dropped.

The biggest case is `readonly`. Every Option-, Setting- or SelectedProgram-backed entity carries it (see [Adding a new entity](entity_descriptions.md#base-entity-hcentitydescription)): appliances lock these to read-only while a program runs, the entity stays available, and a write raises a clear error. The visible-but-locked behavior is easy to defend, since the official app does the same and the cloud integration also keeps read-only entities available and errors on write. The attribute is the hard part: it was added on request in fork issue #59 so templates and cards can show the lock, and dropping it in core takes that away.

Options, to decide before the `select` PR (the first platform with lockable entities):

| Option | For | Against |
| --- | --- | --- |
| Drop the attribute, keep visible-but-locked with the error on write | Matches the cloud integration; nothing for reviewers to object to | Users lose the lock indicator #59 asked for |
| Keep the attribute and explain it in the PR | No feature loss | Likely a review round that ends in dropping it anyway |
| One "Settings locked" binary sensor per appliance | An entity, which core prefers; one entity instead of an attribute on dozens | Only works if the lock is appliance-wide, which isn't confirmed: Options, Settings and SelectedProgram lock at different times (#59). If it isn't, it needs a lock sensor per lockable entity, which would add tons of entities |

**Leaning:** drop the attribute. Check first whether the lock really is appliance-wide (then the binary sensor is an option), and point users to the error message the write raises.

The other attributes (`Is Estimated`, `Auto Counting`, the hob zone `Type`, `Last Start`) follow the same rule: make an entity if it's useful on its own, otherwise drop it.

### Optimistic hood boost

The hood's `fan` entity shows a just-requested boost for 8 seconds before the hood confirms it (`_OPTIMISTIC_PRESET_DURATION` in `fan.py`), because the hood is slow to report it. Core wants entities to follow the device whenever the device reports its own state, and optimistic state is meant for devices that don't. Replace it before the `fan` PR (ideally in v2.0.0): wait in the action until the hood confirms, with a timeout, the way the library's `set_ambient_light()` waits for the hood's light settings.

### Delay start number

The "Delay start" number (v2.0.0, replacing 1.9.0's select from #148 and the Start in / Finish in numbers) holds a delay in minutes that only exists in Home Assistant: the appliance has no such setting, and the Start button turns it into `StartInRelative` (the delay as-is) or `FinishInRelative` (the program's duration plus the delay) when the program starts. The value is restored after a restart and resets after a start. It exists because some appliances only accept a delay as part of the program start: the Siemens WM16XKH2EU washer rejects a direct write even though its device description says it's writable (#146). Which appliances need that can't be read from the device description, only found out by trying the write, so it can't simply be created only where it's needed.

It's one entity per appliance, so there are no longer two controls for one option. The remaining problem for core: **its state lives only in Home Assistant**, not on the appliance, which reviewers usually push back on. The answer is #146: on some appliances the delay can't be stored anywhere else, and its value is always the delay itself, where `FinishInRelative` would be the program's duration plus the delay. A writable "Start in" number was considered (write right away, hold the value only when the appliance refuses), but on `FinishInRelative` appliances the shown value would have to be converted with a duration that changes with the program, and which path an appliance takes would only be known after a failed write.

### Corrections for stale values

Some values are overridden because the appliance leaves them stale, for example program phase and progress, which freeze at their last running value once an appliance powers itself off while staying connected (`_no_active_program_and_off` in `sensor.py`). These correct wrong data instead of hiding real data, so they're fine in core. Each one needs a comment naming the appliance it was confirmed on, and a test.

## Open questions

- Does the core review accept BSH's app client for the account sign-in? There's precedent (`simplisafe`, `roborock`), but BSH deliberately restricts the scopes for local keys to its own client.
- Is `homeconnect_ws` acceptable as a core domain?
- How should the 8 BSH brand virtual integrations (Siemens, Thermador, Neff and so on) point to both integrations?
