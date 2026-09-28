# Core submission plan

This is the plan for getting Home Connect Local into Home Assistant core. It has four phases: what has to be done in the library before the first PR, the initial submission itself, porting everything else afterwards, and what happens to this repository once everything is in core.

Nothing here is scheduled yet. The first phase is blocked on a library rewrite (see [the license blocker](#1-license-the-library-blocker)), so treat this as the order of work, not a timeline.

> [!NOTE]
> Home Assistant's own rules this plan follows: the [review process](https://developers.home-assistant.io/docs/review-process/), the [integration quality scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/) and the [documentation standards](https://developers.home-assistant.io/docs/documenting/standards/). Where this plan and those pages disagree, those pages win.

## Current size

Entity descriptions in `entity_descriptions/`, counted on `dev` on 2026-09-27 (after #117). This number changes with almost every feature PR, so recount before relying on it.

| Platform | Descriptions | Without repeats |
| --- | --- | --- |
| `sensor` | 73 | 71 |
| `binary_sensor` | 74 | 64 |
| `switch` | 83 | 74 |
| `select` | 97 | 97 |
| `number` | 34 | 32 |
| `button` | 12 | 12 |
| `light` | 13 | 7 |
| `fan` | 1 | 1 |
| `update` | 2 | 2 |
| **Total** | **389** | **360** |

- **Descriptions** is every `HC*EntityDescription(...)` in the code.
- **Without repeats** counts each key once. Repeats are the same entity described twice: appliance variants (for example the hood lights), Celsius/Fahrenheit pairs, and the old and new names for the same fridge and washer features that v2.0.0's entity cleanup will merge.
- After v2.0.0's entity cleanup merges the old and new names, drop the **Without repeats** column and keep one count.
- Neither is the number of entities one appliance gets. An appliance only gets the descriptions it reports, and a few descriptions (oven cavities, hob zones) create one entity per cavity or zone.

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

| In the integration today | Moves to |
| --- | --- |
| Hand-built messages: start with Finish-in (`__init__.py`), `fan.py` and `light.py` writes | Library methods (start a program with options, batch value writes) |
| Program and option rules in `helpers.py`: locking, `ensure_writable`, full vs known option sets, unplugged probes | Library `select_program()` / `start_program()` that own these rules |
| `hc_cloud_api.py` and `hc_legacy_oauth.py` (account sign-in and profile fetch) | One library module, something like `home_disconnect.account` (drop the "legacy" name, it's the app's own sign-in) |
| Profile ZIP reading and writing (`config_flow.py`, `export_profile.py`, `hc_cloud_api.py`) | One library profile loader and writer (the simulator can use it too) |
| Clock sync timestamp format | Something like `appliance.set_datetime()` |

Entities, entity descriptions, the config flow UI, storage paths, the error decorator and translations stay in the integration.

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
| Initial platform | `sensor` | Read-only, so none of the program/option write rules have to be reviewed in the first PR. Status sensors (operation state, door, remaining time) exist on nearly every appliance type. |
| Domain | Keep `homeconnect_ws` if reviewers accept it, otherwise pick a new one early | Same domain means custom users can switch without re-adding appliances (see [Phase 4](#phase-4-after-everything-is-ported)). A new domain means everyone re-adds their appliances. `ws` is an implementation detail, so expect reviewers to question it. If it has to change, `home_connect_local` follows core's `powerfox` / `powerfox_local` naming ("Powerfox Cloud" and "Powerfox Local", grouped under one Powerfox brand). |
| Brand | Add the domain to core's existing Bosch brand (`homeassistant/brands/bosch.json`) | Core lists `home_connect` under Bosch, next to `bosch_alarm` and `bosch_shc`, so the local integration belongs in the same brand. There's no Siemens, Thermador or other BSH brand file to add it to. |

### What's in it

- Config flow: the Home Connect sign-in, appliance selection and connection test. Keep the test-before-setup split for washers and dryers, which cut their WiFi when off (see the `quality_scale.yaml` comment).
- The coordinator and connection handling (push updates, heartbeat, reconnect with backoff).
- Zeroconf discovery (`_homeconnect._tcp.local.`). Each appliance is its own config entry, so a discovered appliance that's already set up is ignored. The cloud `home_connect` integration listens for the same service type (and for DHCP), so on a fresh install both integrations can show a discovered card for the same appliance. That's accepted in core: `powerfox` (cloud) and `powerfox_local` both discover the same poweropti devices with the same zeroconf matcher, and both mark `discovery` as done. It's still worth saying in the PR description. Removing discovery from the cloud integration is its code owners' decision, not part of this plan.
- `sensor` entities, without the diagnostic ones. The custom integration has 73 sensor descriptions, and 9 of them are diagnostic: WiFi signal strength, IPv4 and IPv6 address, water and energy forecast, started and completed program counts, the program end trigger and the dishwasher's machine care reminder. Leaving them out also leaves out the WiFi signal sensor, the only entity that polls (`/ni/info`), so the first PR is push-only.
  - That still leaves 64, spread over every appliance type. The plan is to accept that: entity descriptions are declarative data, so most of the review is the entity classes and the coordinator, not the list.
  - If reviewers say 64 is too many, cut by file, not by appliance: keep the 11 shared sensors in `common.py` (operation state, door, power state, active program, remaining, elapsed and estimated time, progress, start in, finish in, flex start) plus the 3 in `dishcare.py` (rinse aid, salt, program phase), 14 in total. Every appliance type reports the shared ones, so no appliance loses support, it just gets fewer sensors at first. Dishwashers keep their own because they're the appliance BSH pushes Home Connect hardest on. The other appliance-specific sensors then come back one family per PR (cooking, laundry, refrigeration, coffee makers). Cutting out whole appliance types isn't needed.
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

### Things to strip from the core copy

- The dev-only "setup from diagnostics dump" path: `CONF_DEV_SETUP_FROM_DUMP`, `CONF_DEV_OVERRIDE_HOST`, `CONF_DEV_OVERRIDE_PSK`, `CONFIG_SCHEMA`, the `HCConfig` / `hass.data` wiring, `process_json_file`, the `setup_from_dump` branch and the placeholder-host fallback that only exists for dump entries.
- The profile ZIP upload step and the `file_upload` after-dependency (if the sign-in is the chosen setup path). It can come back as a follow-up, see Phase 3.
- Every translation file except English: core keeps `strings.json` and translations come from Lokalise. The German requirement in this repository doesn't carry over.
- Anything written defensively for states the data model already rules out. Reviewers ask "why can this be None?", and if the honest answer is "it can't", the code goes.

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

Each `█` is 10%. Take the **Custom** column from [Current size](#current-size) at the time (after v2.0.0 that's the count without duplicates), since the custom integration keeps changing while the port runs.

Suggested order (description counts are how many entity descriptions each platform has; one appliance only gets the ones it reports):

1. **Diagnostics** (the `diagnostics` Gold rule).
2. **The sensors left out of the initial PR:** the 9 diagnostic sensors, and if the 14-sensor fallback was used, the cooking, laundry, refrigeration and coffee maker sensors, one family per PR.
3. **`binary_sensor`** (74 descriptions), split in two:
   - shared, dishwasher and laundry (43): remote start allowed, door, dishwasher and laundry problem events;
   - refrigeration, cooking and coffee makers (31): mostly the fridge and freezer door and alarm sensors.
4. **`select`** (97 descriptions, each a separate entity; the dropdown values aren't counted): program selection and options, including locked (read-only) entities and filtering unavailable programs.
5. **`switch`** (83 descriptions), split in two:
   - shared, dishwasher and laundry (50);
   - cooking, refrigeration and coffee makers (33).
6. **`number`** (34): settings and options.
7. **`button`** (12): Start, Stop, Pause and the rest. After `select`, since starting needs a selected program.
8. **`light`** (13) and **`fan`** (1): hood lighting and venting.
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

Features that are on the custom integration's own roadmap (for example the per-appliance option-value calibration from [discussion #104](https://github.com/vemboy200/homeconnect_local_hass/discussions/104), or a single summary problem entity) go into whichever side is current at the time. Where core's cloud `home_connect` integration has the same limitation, fixing it isn't a condition for the port.

Expect issues from people who remove the custom integration and switch to core before the port is finished: missing entities, and if the domain stayed `homeconnect_ws`, entries that don't load because the custom integration created them with a newer config entry version than core has. Handle those as they come in.

While porting, the custom integration stays the place to try new things. Anything added here before it's ported gets ported in the same way.

## Phase 4: after everything is ported

- **Deprecate the custom integration.** Once core has feature parity, stop adding features here and put a notice at the top of the README pointing to the core integration.
- **Migration guide.** If the domain stayed `homeconnect_ws`, removing the custom integration from HACS and restarting keeps every config entry, device and entity, because the core integration reads the same entries and unique IDs. Document the exact steps and test them on a real install first. If the domain changed, the guide is "remove and re-add each appliance".
- **Issues and discussions.** Point new reports to the core issue tracker. Keep this repository's issues open until the existing ones are resolved or moved.
- **Docs.** The user-facing pages in `docs/integration/` move into the home-assistant.io integration page. Developer notes (`docs/development/`) stay here or move to the library.
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

## Open questions

- Does the core review accept BSH's app client for the account sign-in? There's precedent (`simplisafe`, `roborock`), but BSH deliberately restricts the scopes for local keys to its own client.
- Is `homeconnect_ws` acceptable as a core domain?
- How should the 8 BSH brand virtual integrations (Siemens, Thermador, Neff and so on) point to both integrations?
