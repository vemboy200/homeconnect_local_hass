# Home Connect Local

[![Latest release](https://img.shields.io/github/v/release/vemboy200/homeconnect_local_hass?label=latest%20release)](https://github.com/vemboy200/homeconnect_local_hass/releases/latest)
[![Latest beta](https://img.shields.io/github/v/release/vemboy200/homeconnect_local_hass?include_prereleases&label=latest%20beta)](https://github.com/vemboy200/homeconnect_local_hass/releases)
[![Downloads](https://img.shields.io/github/downloads/vemboy200/homeconnect_local_hass/total?label=downloads)](https://github.com/vemboy200/homeconnect_local_hass/releases)

> [!IMPORTANT]
> Help wanted to make this integration work entirely offline, read more [here](docs/development/emulated-cloud-setup.md).

> [!NOTE]
> This README covers the basics. For everything else (installation details, troubleshooting, automation examples, supported functions) see the [docs folder](docs).

The **Home Connect Local** allows users to integrate their home appliances supporting the [Home Connect](https://www.home-connect.com/global) standard for Bosch and Siemens using direct communication over the local network.

## At a Glance

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=homeconnect_ws)

- **[IoT Class](https://www.home-assistant.io/blog/2016/02/12/classifying-the-internet-of-things/#classifiers):** Local Push
- **[Secondary IoT Class](https://github.com/vemboy200/home-assistant.io/blob/iot-class-revamp-p3/source/_docs/iot_class.markdown) (unoffical thing):** Local Polling: The WiFi signal-strength diagnostic sensor is polled every hour
- **[Internet Requirement](https://github.com/vemboy200/home-assistant.io/blob/iot-class-revamp-p3/source/_docs/requires_internet.markdown) (unoffical thing):** Setup: obtaining your appliance's encryption keys via the [Home Connect Profile Downloader](https://github.com/bruestel/homeconnect-profile-downloader) needs a one-time connection to the Home Connect cloud. Day-to-day operation after that is entirely local and works without an internet connection (see [this idea](docs/development/emulated-cloud-setup.md) for removing even that)
- **[Quality Scale](https://www.home-assistant.io/docs/quality_scale/#-platinum):** 🏆 Platinum
- Current Maintainer: [@vemboy200](https://github.com/vemboy200)
- Original Maintainer: [@chris-mc1](https://github.com/chris-mc1)
- [View known issues](https://github.com/vemboy200/homeconnect_local_hass/issues)
- [Request a feature](docs/integration/support-and-troubleshooting.md#requesting-a-new-feature)
- [home-disconnect](https://github.com/vemboy200/home-disconnect) - a fork of the local WebSocket protocol library this integration talks to appliances through

## Install the Integration

1. Go to the HACS -> Custom Repositories and add this repository as a Custom Repository [See HACS Documentation for help](https://hacs.xyz/docs/faq/custom_repositories/)

2. Click the button bellow and click 'Download' to install the Integration:

    [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?repository=homeconnect_local_hass&owner=vemboy200)

3. Restart Home Assistant.

## Prerequisites

To use this integration, you must first create a Home Connect account and connect your appliances.

## Supported Devices

Any Home Connect device that
1. Allows a local connection (not all do) - see [Getting started](docs/integration/getting-started.md#supported-devices) for the full breakdown of what's confirmed working
2. Is on the same local network as your Home Assistant instance

## Documentation

- **[Getting started](docs/integration/getting-started.md)** — installation and supported devices
- **[Supported functions](docs/integration/supported-functions.md)** — full entity list by appliance type
- **[Use cases and automation examples](docs/integration/use-cases-and-automation-examples.md)**
- **[Support & Troubleshooting](docs/integration/support-and-troubleshooting.md)** — known limitations, requesting a feature, debug logging
- **[Other stuff](docs/integration/other-stuff.md)** — profile export, data updates, actions, integration removal
- **[Important terms](docs/important-terms.md)**

## AI Use Disclaimer

The current maintainer uses AI assistance in development (see [CONTRIBUTING.md](CONTRIBUTING.md#ai-notice)); all changes are tested against real or simulated hardware before a stable release.
