"""Support for GoXLR Utility media players."""

from __future__ import annotations

import logging
from typing import Any

from goxlrutil_api import GoXLRClient
from goxlrutil_api.protocol.responses import FaderStatus, MixerStatus
from goxlrutil_api.protocol.types import MuteState

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GoXLRUtilityDataUpdateCoordinator
from .entity import GoXLRUtilityEntity, GoXLRUtilityMediaPlayerEntityDescription
from .helper import (
    GoXLRMapItem,
    get_goxlr_attr,
    get_goxlr_keys,
    get_map_item,
    get_volume_percentage,
    resolve_channel,
    resolve_fader,
)

_LOGGER = logging.getLogger(__name__)


def _get_fader_map_item(fader_status: Any, key: str) -> GoXLRMapItem | None:
    """Resolve the map item assigned to a fader."""
    channel = get_goxlr_attr(get_goxlr_attr(fader_status, key), "channel", "")
    return get_map_item(channel)


def get_muted(
    data: MixerStatus,
    fader_key: str | None,
) -> bool:
    """Get muted state for a fader."""
    if fader_key is None:
        return False

    fader: FaderStatus = get_goxlr_attr(data.fader_status, fader_key)
    if fader is None:
        return False

    mute_state = get_goxlr_attr(fader, "mute_state")
    return (
        mute_state != MuteState.Unmuted and str(mute_state) != MuteState.Unmuted.value
    )


async def set_muted(
    client: GoXLRClient,
    serial: str | None,
    fader_key: str | None,
    muted: bool,
) -> None:
    """Set muted state for a fader."""
    if serial is None or fader_key is None:
        return

    fader = resolve_fader(fader_key)
    if fader is None:
        return

    await client.set_fader_mute_state(
        serial,
        fader,
        MuteState.MutedToAll if muted else MuteState.Unmuted,
    )


async def set_volume(
    client: GoXLRClient,
    serial: str | None,
    map_item: GoXLRMapItem | None,
    volume: float,
) -> None:
    """Set volume for a fader."""
    if serial is None or map_item is None:
        return

    channel = resolve_channel(map_item.key)
    if channel is None:
        return

    await client.set_volume(
        serial,
        channel,
        max(0, min(255, round(volume * 255))),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GoXLR Utility media players based on a config entry."""
    coordinator: GoXLRUtilityDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    fader_status = get_goxlr_attr(coordinator.data, "fader_status")
    faders: dict[str, GoXLRMapItem | None] = {
        key: _get_fader_map_item(fader_status, key) for key in ("a", "b", "c", "d")
    }

    _LOGGER.debug("Faders: %s", faders)

    media_player_descriptions: list[GoXLRUtilityMediaPlayerEntityDescription] = []

    for key in get_goxlr_keys(coordinator.data.levels.volumes):
        map_item = get_map_item(key)
        fader_key = next(
            (name for name, value in faders.items() if value == map_item),
            None,
        )

        media_player_descriptions.append(
            GoXLRUtilityMediaPlayerEntityDescription(
                key=key,
                name=f"{map_item.name if map_item else key}",
                icon=map_item.icon if map_item else "mdi:volume-high",
                device_class=MediaPlayerDeviceClass.SPEAKER,
                can_mute=fader_key is not None,
                muted_fn=lambda data, fader_key=fader_key: get_muted(data, fader_key),
                volume_pct_fn=lambda data, key=key: get_volume_percentage(data, key),
                set_muted_fn=lambda client, serial, muted, fader_key=fader_key: (
                    set_muted(
                        client,
                        serial,
                        fader_key,
                        muted,
                    )
                ),
                set_volume_fn=lambda client, serial, value, map_item=map_item: (
                    set_volume(
                        client,
                        serial,
                        map_item,
                        value,
                    )
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
            self.coordinator.serial_number,
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
            self.coordinator.serial_number,
            volume,
        )
        await self.coordinator.async_request_refresh()
