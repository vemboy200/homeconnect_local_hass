# Using the official cloud API docs

BSH documents its official cloud API for third-party developers at [api-docs.home-connect.com](https://api-docs.home-connect.com/). The local WebSocket API this integration uses isn't documented, but the two use nearly the same keys and values: an event, setting, status or option has the same name in both (for example `Refrigeration.FridgeFreezer.Event.DoorAlarmFreezer`), and enumerations have the same value names (for example `Present`, `Confirmed` and `Off`). Most likely BSH's engineers share one naming scheme between the two. The main difference is coverage: the cloud API only exposes part of what the appliances report locally.

That makes the cloud docs the best official source for what a key and its values mean.

## Useful pages

- [Events](https://api-docs.home-connect.com/events): alarms and notifications, and the `EventPresentState` enumeration.
- [Programs and options](https://api-docs.home-connect.com/programs-and-options)
- [Settings](https://api-docs.home-connect.com/settings)
- [States](https://api-docs.home-connect.com/states)

## What carries over

- **Meanings.** What a key represents and what each enumeration value means. This is the hardest thing to work out from local data alone.
- **Value names, units and ranges**, as a starting point.
- **Names** for entity translations, when BSH's description is clearer than the key.

## What doesn't

- **Whether a key exists locally.** Local entities only exist when the appliance's own device description lists the key, and a given appliance may not have every key the docs list for its type. A key from the docs is a candidate, not a guarantee.
- **Access.** The integration uses the access from the device description, which can change at runtime (see the `READ` handling in [Adding a new entity](entity_descriptions.md#base-entity-hcentitydescription)), not what the docs say. No difference between cloud and local access has been seen so far.
- **Old names.** Appliances use both older and newer names for some features (for example the older and newer fridge keys). The docs usually only show the current one.
- **Everything the cloud doesn't expose.** Most local-only keys aren't in the docs at all.

## Adding an entity from the docs

1. **Confirm the key exists locally** in a real device description, debug log or diagnostics download. A key that's only in the docs waits until someone reports it.
2. **Use the docs for the meaning**: the name, value mapping, device class and so on.
3. **Link the docs page in the PR.** A link to the documented meaning is a stronger answer to "what does this value mean?" than "we saw it on one appliance", in this repository and in core reviews.

An entity description for a key an appliance doesn't have does nothing on that appliance: no entity is created. So the risk in adding one is getting the mapping wrong on the appliances that do have it, which is why step 1 comes first.
