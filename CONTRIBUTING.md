# Contributing

Thanks for considering a contribution to Home Connect Local!

## Before you start

Every entity in this integration has to be reverse engineered from a real appliance's profile data, see [Requesting a New Feature](docs/integration/support-and-troubleshooting.md#requesting-a-new-feature) for what that involves if you're adding support for something new.

## Adding or changing an entity

See [docs/development/entity_descriptions.md](docs/development/entity_descriptions.md) for the entity description fields available per platform (select, switch, sensor, etc.), and [docs/development/us_appliances.md](docs/development/us_appliances.md) for US-specific (Fahrenheit) quirks already discovered.

Testing against a real appliance is strongly preferred if possible. The [HomeConnect Websocket Simulator](https://github.com/chris-mc1/homeconnect_ws_sim/) can help for some cases. See the dev-only `configuration.yaml` options in [docs/development/entity_descriptions.md](docs/development/entity_descriptions.md#development-options).

## Docs live in the same PR as the feature

If your PR adds a user-facing entity or feature, update [docs/integration/supported-functions.md](docs/integration/supported-functions.md) in the same PR, not as a follow-up. Docs that lag behind the code are worse than no docs.

## Checklist

The PR template covers the specifics. In short: `icons.json`, `translations/en.json` and `translations/de.json` (German is required alongside English), and the relevant `docs/` page, whichever apply to your change.

## Ai notice

AI generated code is acceptable, as long as it is tried against a real system. I personally also use AI in my development, but when making docs changes, it is preferable not to use AI.

## Try to keep PRs small and focused

Generally it is a good idea to try to keep your pr as small and focused as possible. Although huge prs (up to 1000 lines changed excluding docs), are allowed it is best to keep your pr as small as possible.
