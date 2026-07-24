"""Description for all supported Entities."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from custom_components.homeconnect_ws.helpers import merge_dicts

from .common import COMMON_ENTITY_DESCRIPTIONS
from .consumer_products import CONSUMER_PRODUCTS_ENTITY_DESCRIPTIONS
from .cooking import COOKING_ENTITY_DESCRIPTIONS
from .descriptions_definitions import (
    EntityDescriptions,
    HCBinarySensorEntityDescription,
    HCButtonEntityDescription,
    HCEntityDescription,
    HCFanEntityDescription,
    HCLightEntityDescription,
    HCNumberEntityDescription,
    HCSelectEntityDescription,
    HCSensorEntityDescription,
    HCSwitchEntityDescription,
    HCUpdateEntityDescription,
    _EntityDescriptionsDefinitionsType,
    _EntityDescriptionsType,
)
from .dishcare import DISHCARE_ENTITY_DESCRIPTIONS
from .laundry_care import LAUNDRY_ENTITY_DESCRIPTIONS
from .refrigeration import REFRIGERATION_ENTITY_DESCRIPTIONS

if TYPE_CHECKING:
    from collections.abc import Callable

    from home_disconnect import HomeAppliance


ALL_ENTITY_DESCRIPTIONS: _EntityDescriptionsDefinitionsType | None = None


def get_all_entity_description() -> _EntityDescriptionsDefinitionsType:
    global ALL_ENTITY_DESCRIPTIONS  # noqa: PLW0603
    if ALL_ENTITY_DESCRIPTIONS is None:
        ALL_ENTITY_DESCRIPTIONS = merge_dicts(
            COMMON_ENTITY_DESCRIPTIONS,
            CONSUMER_PRODUCTS_ENTITY_DESCRIPTIONS,
            COOKING_ENTITY_DESCRIPTIONS,
            DISHCARE_ENTITY_DESCRIPTIONS,
            LAUNDRY_ENTITY_DESCRIPTIONS,
            REFRIGERATION_ENTITY_DESCRIPTIONS,
        )
    return ALL_ENTITY_DESCRIPTIONS


def _resolve_description(
    description: HCEntityDescription
    | Callable[[HomeAppliance], HCEntityDescription | EntityDescriptions | None],
    appliance: HomeAppliance,
) -> HCEntityDescription | None:
    """
    Resolve a single per-type description entry to a concrete instance, if any.

    Note: HA's frozen_or_thawed EntityDescription machinery clones these
    classes into homeassistant.util.frozen_dataclass_compat at runtime, so
    isinstance() checks against HCEntityDescription (or any subclass) are
    unreliable here - callable() duck-typing is the only thing that actually
    distinguishes a description instance from a per-appliance generator
    function.
    """
    if not callable(description):
        return description
    dynamic_result = description(appliance)
    if not dynamic_result:
        return None
    return cast("HCEntityDescription", dynamic_result)


def get_available_entities(appliance: HomeAppliance) -> _EntityDescriptionsType:
    """Get all available Entity descriptions."""
    available_entities: _EntityDescriptionsType = {
        "button": [],
        "active_program": [],
        "binary_sensor": [],
        "event_sensor": [],
        "number": [],
        "program": [],
        "select": [],
        "sensor": [],
        "start_button": [],
        "switch": [],
        "wifi": [],
        "light": [],
        "fan": [],
        "update": [],
    }
    appliance_entities = set(appliance.entities)
    for description_type, descriptions in get_all_entity_description().items():
        # dynamic descriptions: each callable builds a full set of new
        # entities (across types) for this specific appliance.
        if description_type == "dynamic":
            for descriptions_fn in descriptions:
                if not callable(descriptions_fn):
                    continue
                dynamic_result = descriptions_fn(appliance)
                if not isinstance(dynamic_result, dict):
                    continue
                dynamic_descriptions = cast("_EntityDescriptionsType", dynamic_result)
                for key, value in dynamic_descriptions.items():
                    available_entities[key].extend(value)
            continue
        for description in descriptions:
            resolved_description = _resolve_description(description, appliance)
            if resolved_description is None:
                continue
            all_subscribed_entities: set[str] = set()
            if resolved_description.entity:
                all_subscribed_entities.add(resolved_description.entity)
            if resolved_description.entities:
                all_subscribed_entities.update(resolved_description.entities)
            if appliance_entities.issuperset(all_subscribed_entities):
                available_entities[description_type].append(resolved_description)
    return available_entities


__all__ = [
    "EntityDescriptions",
    "HCBinarySensorEntityDescription",
    "HCButtonEntityDescription",
    "HCEntityDescription",
    "HCFanEntityDescription",
    "HCLightEntityDescription",
    "HCNumberEntityDescription",
    "HCSelectEntityDescription",
    "HCSensorEntityDescription",
    "HCSwitchEntityDescription",
    "HCUpdateEntityDescription",
    "_EntityDescriptionsType",
    "get_available_entities",
]
