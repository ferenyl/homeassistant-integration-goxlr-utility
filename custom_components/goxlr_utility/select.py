"""Support for GoXLR Utility select entities."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from goxlrutil_api import GoXLRClient
from goxlrutil_api.protocol.responses import MixerStatus

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GoXLRUtilityDataUpdateCoordinator
from .entity import GoXLRUtilityEntity


@dataclass(frozen=True, kw_only=True)
class GoXLRUtilitySelectEntityDescription(SelectEntityDescription):
    """Describe a GoXLR Utility select entity."""

    options_fn: Callable[[GoXLRClient, str], Awaitable[list[str]]]
    current_fn: Callable[[MixerStatus], str | None]
    select_fn: Callable[[GoXLRClient, str, str], Awaitable[None]]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GoXLR Utility profile selects based on a config entry."""
    coordinator: GoXLRUtilityDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    descriptions: list[GoXLRUtilitySelectEntityDescription] = [
        GoXLRUtilitySelectEntityDescription(
            key="profile_select",
            name="Profile",
            icon="mdi:playlist-play",
            options_fn=lambda client, serial: client.list_profiles(serial),
            current_fn=lambda data: data.profile_name,
            select_fn=lambda client, serial, option: client.load_profile(
                serial, option
            ),
        ),
        GoXLRUtilitySelectEntityDescription(
            key="microphone_profile_select",
            name="Microphone profile",
            icon="mdi:microphone-settings",
            options_fn=lambda client, serial: client.list_mic_profiles(serial),
            current_fn=lambda data: data.mic_profile_name,
            select_fn=lambda client, serial, option: client.load_mic_profile(
                serial, option
            ),
        ),
    ]

    entities = [
        GoXLRUtilitySelect(
            coordinator,
            description,
            entry.data.copy(),
        )
        for description in descriptions
    ]

    async_add_entities(entities)


class GoXLRUtilitySelect(GoXLRUtilityEntity, SelectEntity):
    """Define a GoXLR Utility select entity."""

    entity_description: GoXLRUtilitySelectEntityDescription

    def __init__(
        self,
        coordinator: GoXLRUtilityDataUpdateCoordinator,
        description: GoXLRUtilitySelectEntityDescription,
        entry_data: dict[str, object],
    ) -> None:
        """Initialize the select entity."""
        super().__init__(
            coordinator,
            entry_data,
            description.key,
            description.name,
        )
        self.entity_description = description
        self._attr_options = []

    @property
    def current_option(self) -> str | None:
        """Return the currently selected option."""
        return self.entity_description.current_fn(self.coordinator.data)

    async def async_added_to_hass(self) -> None:
        """Fetch the initial list of available options."""
        await super().async_added_to_hass()
        await self._async_refresh_options()

    async def _async_refresh_options(self) -> None:
        """Refresh the available select options from the device."""
        if self.coordinator.client is None:
            return

        serial = self.coordinator.serial_number
        if serial is None:
            return

        self._attr_options = await self.entity_description.options_fn(
            self.coordinator.client,
            serial,
        )

    async def async_select_option(self, option: str) -> None:
        """Select a new profile option."""
        if self.coordinator.client is None:
            return

        serial = self.coordinator.serial_number
        if serial is None:
            return

        await self.entity_description.select_fn(
            self.coordinator.client,
            serial,
            option,
        )
        await self._async_refresh_options()
        await self.coordinator.async_request_refresh()
