"""Support for GoXLR Utility routing switches."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GoXLRUtilityDataUpdateCoordinator
from .entity import GoXLRUtilityEntity, GoXLRUtilitySwitchEntityDescription
from .helper import (
    get_goxlr_attr,
    get_map_item,
    normalize_key,
    resolve_input,
    resolve_output,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GoXLR Utility routing switches based on a config entry."""
    coordinator: GoXLRUtilityDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    route_descriptions: list[GoXLRUtilitySwitchEntityDescription] = []
    router = get_goxlr_attr(coordinator.data, "router", {})

    input_keys = [
        str(key)
        for key in (
            router.keys()
            if isinstance(router, dict)
            else getattr(router, "__dict__", {}).keys()
        )
        if not str(key).startswith("_")
    ]
    all_output_keys: set[str] = set()

    for input_key in input_keys:
        outputs = get_goxlr_attr(router, input_key, {})
        output_keys = (
            outputs.keys()
            if isinstance(outputs, dict)
            else getattr(outputs, "__dict__", {}).keys()
        )
        all_output_keys.update(
            str(key) for key in output_keys if not str(key).startswith("_")
        )

    for output_key in sorted(all_output_keys):
        output_map_item = get_map_item(output_key)

        for input_key in sorted(input_keys):
            outputs = get_goxlr_attr(router, input_key, {})
            if get_goxlr_attr(outputs, output_key) is None:
                continue

            input_map_item = get_map_item(input_key)
            route_descriptions.append(
                GoXLRUtilitySwitchEntityDescription(
                    key=(
                        f"route_{normalize_key(input_key)}_to_"
                        f"{normalize_key(output_key)}"
                    ),
                    name=(
                        f"{output_map_item.name if output_map_item else output_key}: "
                        f"{input_map_item.name if input_map_item else input_key}"
                    ),
                    icon=(
                        output_map_item.icon
                        if output_map_item and output_map_item.icon
                        else "mdi:swap-horizontal"
                    ),
                    route_input=input_key,
                    route_output=output_key,
                )
            )

    async_add_entities(
        [
            GoXLRUtilitySwitch(
                coordinator,
                description,
                entry.data.copy(),
            )
            for description in route_descriptions
        ]
    )


class GoXLRUtilitySwitch(GoXLRUtilityEntity, SwitchEntity):
    """Define a GoXLR Utility routing switch."""

    entity_description: GoXLRUtilitySwitchEntityDescription

    def __init__(
        self,
        coordinator: GoXLRUtilityDataUpdateCoordinator,
        description: GoXLRUtilitySwitchEntityDescription,
        entry_data: dict[str, object],
    ) -> None:
        """Initialize the routing switch."""
        super().__init__(
            coordinator,
            entry_data,
            description.key,
            description.name,
        )
        self.entity_description = description

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return descriptive route metadata."""
        input_map_item = get_map_item(self.entity_description.route_input)
        output_map_item = get_map_item(self.entity_description.route_output)
        return {
            "input": input_map_item.name
            if input_map_item
            else self.entity_description.route_input,
            "output": output_map_item.name
            if output_map_item
            else self.entity_description.route_output,
        }

    @property
    def is_on(self) -> bool:
        """Return whether this route is enabled."""
        router = get_goxlr_attr(self.coordinator.data, "router", {})
        outputs = get_goxlr_attr(router, self.entity_description.route_input, {})
        return bool(
            get_goxlr_attr(outputs, self.entity_description.route_output, False)
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the route."""
        await self._async_set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the route."""
        await self._async_set_enabled(False)

    async def _async_set_enabled(self, enabled: bool) -> None:
        """Enable or disable the route."""
        if self.coordinator.client is None:
            return

        serial = self.coordinator.serial_number
        if serial is None:
            return

        route_input = resolve_input(self.entity_description.route_input)
        route_output = resolve_output(self.entity_description.route_output)
        if route_input is None or route_output is None:
            return

        await self.coordinator.client.set_router(
            serial,
            route_input,
            route_output,
            enabled,
        )
        await self.coordinator.async_request_refresh()
