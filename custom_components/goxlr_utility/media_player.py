"""Support for GoXLR Utility media players."""

from __future__ import annotations

import logging
from typing import Any

from goxlrutilityapi.const import MUTED_STATE, NAME_MAP
from goxlrutilityapi.helpers import get_volume_percentage
from goxlrutilityapi.models.map_item import MapItem
from goxlrutilityapi.models.status import FaderStatus, Mixer
from goxlrutilityapi.websocket_client import WebsocketClient

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import compat  # noqa: F401
from .const import DOMAIN
from .coordinator import GoXLRUtilityDataUpdateCoordinator
from .entity import GoXLRUtilityEntity, GoXLRUtilityMediaPlayerEntityDescription
from .helper import get_goxlr_attr, get_goxlr_keys

_LOGGER = logging.getLogger(__name__)


def _get_fader_map_item(fader_status: Any, key: str) -> MapItem | None:
    """Resolve the map item assigned to a fader."""
    channel = str(get_goxlr_attr(get_goxlr_attr(fader_status, key), "channel", ""))
    return NAME_MAP.get(channel) or NAME_MAP.get(channel.lower())


def get_muted(
    data: Mixer,
    fader_key: str | None,
) -> bool:
    """Get muted state for a fader."""
    if fader_key is None:
        return False

    fader: FaderStatus = get_goxlr_attr(data.fader_status, fader_key)
    if fader is None:
        return False

    return fader.mute_state == MUTED_STATE


async def set_muted(
    client: WebsocketClient,
    fader_key: str | None,
    muted: bool,
) -> None:
    """Set muted state for a fader."""
    if fader_key is None:
        return

    await client.set_muted(
        fader_key.capitalize(),
        muted,
    )


async def set_volume(
    client: WebsocketClient,
    map_item: MapItem | None,
    volume: float,
) -> None:
    """Set volume for a fader."""
    if map_item is None:
        return

    await client.set_volume(
        map_item.key,
        max(0, min(255, round(volume * 2.55))),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GoXLR Utility media players based on a config entry."""
    coordinator: GoXLRUtilityDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    fader_status = get_goxlr_attr(coordinator.data, "fader_status")
    faders: dict[str, MapItem | None] = {
        key: _get_fader_map_item(fader_status, key) for key in ("a", "b", "c", "d")
    }

    _LOGGER.debug("Faders: %s", faders)

    media_player_descriptions: list[GoXLRUtilityMediaPlayerEntityDescription] = []

    for key in get_goxlr_keys(coordinator.data.levels.volumes):
        _LOGGER.debug("key: %s", key)

        # Get map item from map
        map_item: MapItem | None = NAME_MAP.get(key)
        _LOGGER.debug("Map item: %s", map_item)

        # Get fader key from map item
        fader_key = next(
            (key for key, value in faders.items() if value == map_item), None
        )
        _LOGGER.debug("Fader key: %s", fader_key)

        media_player_descriptions.append(
            GoXLRUtilityMediaPlayerEntityDescription(
                key=key,
                name=f"{map_item.name if map_item else key}",
                icon=map_item.icon if map_item else "mdi:volume-high",
                device_class=MediaPlayerDeviceClass.SPEAKER,
                can_mute=fader_key is not None,
                muted_fn=lambda data, fader_key=fader_key: get_muted(data, fader_key),
                volume_pct_fn=lambda data, key=key: get_volume_percentage(data, key),
                set_muted_fn=lambda client, muted, fader_key=fader_key: set_muted(
                    client,
                    fader_key,
                    muted,
                ),
                set_volume_fn=lambda client, value, map_item=map_item: set_volume(
                    client,
                    map_item,
                    value,
                ),
            )
        )

    entities = [
        GoXLRUtilityMediaPlayer(
            coordinator,
            description,
            entry.data.copy(),
        )
        for description in media_player_descriptions
    ]

    async_add_entities(entities)


class GoXLRUtilityMediaPlayer(GoXLRUtilityEntity, MediaPlayerEntity):
    """Define a GoXLR Utility media_player."""

    entity_description: GoXLRUtilityMediaPlayerEntityDescription

    def __init__(
        self,
        coordinator: GoXLRUtilityDataUpdateCoordinator,
        description: GoXLRUtilityMediaPlayerEntityDescription,
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
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Flag media player features that are supported."""
        if self.entity_description.can_mute:
            return (
                MediaPlayerEntityFeature.VOLUME_SET
                | MediaPlayerEntityFeature.VOLUME_MUTE
            )
        return MediaPlayerEntityFeature.VOLUME_SET

    @property
    def state(self) -> MediaPlayerState | None:
        """State of the player."""
        return (
            MediaPlayerState.IDLE if self.is_volume_muted else MediaPlayerState.PLAYING
        )

    @property
    def volume_level(self) -> float | None:
        """Volume level of the media player (0..1)."""
        if (
            volume_pct := self.entity_description.volume_pct_fn(self.coordinator.data)
        ) is None:
            return None
        return volume_pct / 100

    @property
    def is_volume_muted(self) -> bool | None:
        """Boolean if volume is currently muted."""
        return self.entity_description.muted_fn(self.coordinator.data)

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        if self.coordinator.client is None:
            return

        await self.entity_description.set_muted_fn(
            self.coordinator.client,
            mute,
        )
        await self.coordinator.async_request_refresh()

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        if self.coordinator.client is None:
            return

        if self.is_volume_muted:
            await self.async_mute_volume(False)

        await self.entity_description.set_volume_fn(
            self.coordinator.client,
            volume * 100,
        )
        await self.coordinator.async_request_refresh()
