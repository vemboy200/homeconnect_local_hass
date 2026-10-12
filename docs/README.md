# Home Connect Local

[![Latest release](https://img.shields.io/github/v/release/vemboy200/homeconnect_local_hass?label=latest%20release)](https://github.com/vemboy200/homeconnect_local_hass/releases/latest)
[![Latest beta](https://img.shields.io/github/v/release/vemboy200/homeconnect_local_hass?include_prereleases&label=latest%20beta)](https://github.com/vemboy200/homeconnect_local_hass/releases)
[![Downloads](https://img.shields.io/github/downloads/vemboy200/homeconnect_local_hass/total?label=downloads)](https://github.com/vemboy200/homeconnect_local_hass/releases)

The **Home Connect Local** allows users to integrate their home appliances supporting the  [Home Connect](https://www.home-connect.com/global) standard for Bosch and Siemens using direct communication over the local network.

New here? Start with:

- **[Important terms](important-terms.md)**: terminology used throughout these docs
- **[Getting started](integration/getting-started.md)**: installation and supported devices

## The actual integration itself

- **[Supported functions](integration/supported-functions.md)**: full entity list by appliance type
- **[Use cases and automation examples](integration/use-cases-and-automation-examples.md)**
- **[Support & Troubleshooting](integration/support-and-troubleshooting.md)**: known limitations, requesting a feature, debug logging
- **[Other stuff](integration/other-stuff.md)**: profile export, data updates, actions, integration removal

## For contributors

- **[Contributing guidelines](../CONTRIBUTING.md)**: the general guidelines for contributing
- **[Adding a new entity](development/entity_descriptions.md)**: entity description fields by platform, dev-only config options
- **[Using the official cloud API docs](development/official-api-docs.md)**: what BSH's documentation for the cloud API tells you about the local API
- **[US appliance notes](development/us_appliances.md)**: appliance-specific reverse-engineering details
- **[Core submission plan](development/core-submission-plan.md)**: what has to happen before, during and after submitting this integration to Home Assistant core
- **[Idea: emulating the cloud during setup](development/emulated-cloud-setup.md)**: unclaimed project idea for removing the last internet dependency (initial pairing)

## Quick stats

- **[IoT Class](https://www.home-assistant.io/blog/2016/02/12/classifying-the-internet-of-things/#classifiers):** Local Push
- **[Secondary IoT Class](https://github.com/vemboy200/home-assistant.io/blob/iot-class-revamp-p3/source/_docs/iot_class.markdown) (unoffical thing):** Local Polling: The WiFi signal-strength diagnostic sensor is polled every hour
- **[Internet Requirement](https://github.com/vemboy200/home-assistant.io/blob/iot-class-revamp-p3/source/_docs/requires_internet.markdown) (unoffical thing):** Setup: obtaining your appliance's encryption keys via the [Home Connect Profile Downloader](https://github.com/bruestel/homeconnect-profile-downloader) needs a one-time connection to the Home Connect cloud. Day-to-day operation after that is entirely local and works without an internet connection (see [this idea](development/emulated-cloud-setup.md) for removing even that)
- **[Quality Scale](https://www.home-assistant.io/docs/quality_scale/#-platinum):** 🏆 Platinum
- Current Maintainer: [@vemboy200](https://github.com/vemboy200)
- Original Maintainer:[@chris-mc1](https://github.com/chris-mc1)
- [View source on GitHub](https://github.com/vemboy200/homeconnect_local_hass)
- [View known issues](https://github.com/vemboy200/homeconnect_local_hass/issues)
- [Request a feature](integration/support-and-troubleshooting.md#requesting-a-new-feature)
- [home-disconnect](https://github.com/vemboy200/home-disconnect) - a fork of the local WebSocket protocol library this integration talks to appliances through

## Maintiance note

This is a fork of [chris-mc1's repo](https://github.com/chris-mc1/homeconnect_local_hass) after they may have abandoned the integration.

I am maintaining this integration because

- I have some kind of weird obsession with smart appliances for some reason
- Because of [Jeff Geerling's frustration with his bosch 500 dishwasher](https://youtu.be/5M_hmwBBPnc?si=5VKBdr38sbwJL5Sg) which I'll summarize in the image below

<img width="1920" alt="Critizing Home Connect 001" src="https://github.com/user-attachments/assets/19a42649-cc47-4e8d-83c7-c00c64e6fd27" />

Do you want to know the worst part though? My dishwasher, the Thermador DWHD660WFP has Home Connect and all functions ON THE PHYSICAL PANEL, aka I dont need to connect my dishwasher to my wifi to run a rinse cycle. I can but I don't need to. This is ridiculous BSH, you didn't need to remove the buttons and force people to use Home Connect.
