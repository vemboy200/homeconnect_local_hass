## Description

<!-- What does this PR do, and why? -->

## Checklist

- [ ] This has been tested against a real appliance
- [ ] If this adds/changes an entity: the `icons.json` file has been updated
- [ ] If this adds/changes an entity: the `translations/en.json` and `translations/de.json` files have been updated (English is the reference locale, and German is required too: Germany has the most Home Assistant installations and is BSH's home market. CI fails if `de.json` is missing a key from `en.json`. Other languages are welcome but not required, a maintainer can fill those in)
- [ ] If this adds a new user-facing entity/feature: the [docs/integration/supported-functions.md](../docs/integration/supported-functions.md) had been updated
- [ ] If this changes how entity descriptions work: the [docs/development/entity_descriptions.md](../docs/development/entity_descriptions.md) had been updated
