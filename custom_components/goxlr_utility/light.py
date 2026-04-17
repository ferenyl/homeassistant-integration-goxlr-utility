"""Support for GoXLR Utility lights."""

from __future__ import annotations

import logging
from typing import Any, cast

from goxlrutilityapi.const import KEY_MAP, NAME_MAP
from goxlrutilityapi.models.map_item import MapItem

from homeassistant.components.light import ATTR_RGB_COLOR, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.color as color_util

from . import compat  # noqa: F401
from .const import DOMAIN
from .coordinator import GoXLRUtilityDataUpdateCoordinator
from .entity import GoXLRUtilityEntity, GoXLRUtilityLightEntityDescription, ItemType
from .helper import get_goxlr_attr, get_goxlr_keys

_LOGGER = logging.getLogger(__name__)


def _get_item_colour(
    data: Any, collection: str, item_key: str, colour: str
) -> str | None:
    """Return a light colour from the normalized GoXLR data."""
    lighting_collection = get_goxlr_attr(data.lighting, collection)
    item = get_goxlr_attr(lighting_collection, item_key)
    item_colours = get_goxlr_attr(item, "colours")
    return get_goxlr_attr(item_colours, colour)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GoXLR Utility light based on a config entry."""
    coordinator: GoXLRUtilityDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    light_descriptions = [
        GoXLRUtilityLightEntityDescription(
            key="light_accent",
            name="Accent",
            icon="mdi:television-ambient-light",
            item_type=ItemType.ACCENT,
        ),
    ]

    for key in get_goxlr_keys(coordinator.data.lighting.buttons):
        button_map_item: MapItem | None = NAME_MAP.get(key) or NAME_MAP.get(key.lower())
        light_descriptions.extend(
            [
                GoXLRUtilityLightEntityDescription(
                    key=f"light_button_{key}_active",
                    name=f"{button_map_item.name if button_map_item and button_map_item.name else key} active",
                    icon=button_map_item.icon
                    if button_map_item and button_map_item.icon
                    else None,
                    item_type=ItemType.BUTTON_ACTIVE,
                    item_key=key,
                ),
                GoXLRUtilityLightEntityDescription(
                    key=f"light_button_{key}_inactive",
                    name=f"{button_map_item.name if button_map_item and button_map_item.name else key} inactive",
                    icon=button_map_item.icon
                    if button_map_item and button_map_item.icon
                    else None,
                    item_type=ItemType.BUTTON_INACTIVE,
                    item_key=key,
                ),
            ]
        )

    for key in get_goxlr_keys(coordinator.data.lighting.faders):
        fader_map_item: MapItem | None = NAME_MAP.get(key) or NAME_MAP.get(key.lower())
        light_descriptions.extend(
            [
                GoXLRUtilityLightEntityDescription(
                    key=f"light_fader_{key}_top",
                    name=f"{fader_map_item.name if fader_map_item and fader_map_item.name else key} top",
                    icon=fader_map_item.icon
                    if fader_map_item and fader_map_item.icon
                    else None,
                    item_type=ItemType.FADER_TOP,
                    item_key=key,
                ),
                GoXLRUtilityLightEntityDescription(
                    key=f"light_fader_{key}_bottom",
                    name=f"{fader_map_item.name if fader_map_item and fader_map_item.name else key} bottom",
                    icon=fader_map_item.icon
                    if fader_map_item and fader_map_item.icon
                    else None,
                    item_type=ItemType.FADER_BOTTOM,
                    item_key=key,
                ),
            ]
        )

    entities = [
        GoXLRUtilityLight(
            coordinator,
            description,
            entry.data.copy(),
        )
        for description in light_descriptions
    ]

    async_add_entities(entities)


class GoXLRUtilityLight(GoXLRUtilityEntity, LightEntity):
    """Define a GoXLR Utility light."""

    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}
    entity_description: GoXLRUtilityLightEntityDescription

    def __init__(
        self,
        coordinator: GoXLRUtilityDataUpdateCoordinator,
        description: GoXLRUtilityLightEntityDescription,
        entry_data: dict[str, Any],
    ) -> None:
        """Initialize."""
        super().__init__(
            coordinator,
            entry_data,
            description.key,
            description.name,
        )
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return the state of the light."""
        return self.rgb_color != (0, 0, 0)

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the rgb color value [int, int, int]."""
        hex_value: str | None = None
        if self.entity_description.item_type == ItemType.ACCENT:
            simple = get_goxlr_attr(self.coordinator.data.lighting, "simple")
            accent = get_goxlr_attr(simple, "accent")
            hex_value = get_goxlr_attr(accent, "colour_one")
        elif self.entity_description.item_type == ItemType.BUTTON_ACTIVE:
            hex_value = _get_item_colour(
                self.coordinator.data,
                "buttons",
                self.entity_description.item_key,
                "colour_one",
            )
        elif self.entity_description.item_type == ItemType.BUTTON_INACTIVE:
            hex_value = _get_item_colour(
                self.coordinator.data,
                "buttons",
                self.entity_description.item_key,
                "colour_two",
            )
        elif self.entity_description.item_type == ItemType.FADER_TOP:
            hex_value = _get_item_colour(
                self.coordinator.data,
                "faders",
                self.entity_description.item_key,
                "colour_one",
            )
        elif self.entity_description.item_type == ItemType.FADER_BOTTOM:
            hex_value = _get_item_colour(
                self.coordinator.data,
                "faders",
                self.entity_description.item_key,
                "colour_two",
            )

        return (
            cast(tuple[int, int, int], tuple(color_util.rgb_hex_to_rgb_list(hex_value)))
            if hex_value
            else None
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        if self.coordinator.client is None:
            return

        hex_value = color_util.color_rgb_to_hex(
            *kwargs.get(ATTR_RGB_COLOR, (255, 255, 255))
        )

        if self.entity_description.item_type == ItemType.ACCENT:
            await self.coordinator.client.set_accent_color(hex_value)
            await self.coordinator.async_request_refresh()
            return

        item_key = self.entity_description.item_key
        if (key := KEY_MAP.get(item_key) or KEY_MAP.get(str(item_key).lower())) is None:
            return

        if self.entity_description.item_type == ItemType.BUTTON_ACTIVE:
            await self.coordinator.client.set_button_color(
                key,
                hex_value,
                _get_item_colour(
                    self.coordinator.data, "buttons", item_key, "colour_two"
                )
                or "000000",
            )
        elif self.entity_description.item_type == ItemType.BUTTON_INACTIVE:
            await self.coordinator.client.set_button_color(
                key,
                _get_item_colour(
                    self.coordinator.data, "buttons", item_key, "colour_one"
                )
                or "000000",
                hex_value,
            )
        elif self.entity_description.item_type == ItemType.FADER_TOP:
            await self.coordinator.client.set_fader_color(
                key,
                hex_value,
                _get_item_colour(
                    self.coordinator.data, "faders", item_key, "colour_two"
                )
                or "000000",
            )
        elif self.entity_description.item_type == ItemType.FADER_BOTTOM:
            await self.coordinator.client.set_fader_color(
                key,
                _get_item_colour(
                    self.coordinator.data, "faders", item_key, "colour_one"
                )
                or "000000",
                hex_value,
            )

        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        if self.coordinator.client is None:
            return

        if self.entity_description.item_type == ItemType.ACCENT:
            await self.coordinator.client.set_accent_color("000000")
            await self.coordinator.async_request_refresh()
            return

        item_key = self.entity_description.item_key
        if (key := KEY_MAP.get(item_key) or KEY_MAP.get(str(item_key).lower())) is None:
            return

        if self.entity_description.item_type == ItemType.BUTTON_ACTIVE:
            await self.coordinator.client.set_button_color(
                key,
                "000000",
                _get_item_colour(
                    self.coordinator.data, "buttons", item_key, "colour_two"
                )
                or "000000",
            )
        elif self.entity_description.item_type == ItemType.BUTTON_INACTIVE:
            await self.coordinator.client.set_button_color(
                key,
                _get_item_colour(
                    self.coordinator.data, "buttons", item_key, "colour_one"
                )
                or "000000",
                "000000",
            )
        elif self.entity_description.item_type == ItemType.FADER_TOP:
            await self.coordinator.client.set_fader_color(
                key,
                "000000",
                _get_item_colour(
                    self.coordinator.data, "faders", item_key, "colour_two"
                )
                or "000000",
            )
        elif self.entity_description.item_type == ItemType.FADER_BOTTOM:
            await self.coordinator.client.set_fader_color(
                key,
                _get_item_colour(
                    self.coordinator.data, "faders", item_key, "colour_one"
                )
                or "000000",
                "000000",
            )

        await self.coordinator.async_request_refresh()
