"""Helper for GoXLR Utility integration."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from enum import Enum
import logging
import re
from typing import Any, TypeVar

from goxlrutil_api import GoXLRClient, WebSocketTransport
from goxlrutil_api.protocol.types import (
    Button,
    ChannelName,
    FaderName,
    InputDevice,
    OutputDevice,
)
import httpx

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.httpx_client import get_async_client

from .const import CONNECTION_ERRORS

_LOGGER = logging.getLogger(__name__)

EnumT = TypeVar("EnumT", bound=Enum)


@dataclass(frozen=True, slots=True)
class GoXLRMapItem:
    """Metadata for GoXLR channels, faders, and buttons."""

    key: str
    name: str
    icon: str | None = None


def normalize_key(key: str) -> str:
    """Normalize GoXLR keys to Python-style snake_case."""
    if len(key) == 1 and key.isupper():
        return key.lower()

    normalized = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", key)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", normalized).lower()


def _register_map_item(items: dict[str, GoXLRMapItem], item: GoXLRMapItem) -> None:
    """Register exact and normalized lookup keys for a map item."""
    for key in (item.key, normalize_key(item.key)):
        items[key] = item


NAME_MAP: dict[str, GoXLRMapItem] = {}
for map_item in (
    GoXLRMapItem("Mic", "Microphone", "mdi:microphone"),
    GoXLRMapItem("Microphone", "Microphone", "mdi:microphone"),
    GoXLRMapItem("LineIn", "Line In", "mdi:audio-input-stereo-minijack"),
    GoXLRMapItem("Console", "Console", "mdi:gamepad-variant"),
    GoXLRMapItem("System", "System", "mdi:laptop"),
    GoXLRMapItem("Game", "Game", "mdi:controller-classic"),
    GoXLRMapItem("Chat", "Chat", "mdi:chat"),
    GoXLRMapItem("Sample", "Sample", "mdi:music-note"),
    GoXLRMapItem("Samples", "Samples", "mdi:music-note"),
    GoXLRMapItem("Music", "Music", "mdi:music-clef-treble"),
    GoXLRMapItem("Headphones", "Headphones", "mdi:headphones"),
    GoXLRMapItem("BroadcastMix", "Broadcast Mix", "mdi:broadcast"),
    GoXLRMapItem("ChatMic", "Chat Mic", "mdi:microphone-message"),
    GoXLRMapItem("Sampler", "Sampler", "mdi:playlist-music"),
    GoXLRMapItem("StreamMix2", "Stream Mix 2", "mdi:broadcast"),
    GoXLRMapItem("MicMonitor", "Microphone Monitor", "mdi:ear-hearing"),
    GoXLRMapItem("LineOut", "Line Out", "mdi:audio-video"),
    GoXLRMapItem("A", "Fader 1", "mdi:tune-vertical"),
    GoXLRMapItem("B", "Fader 2", "mdi:tune-vertical"),
    GoXLRMapItem("C", "Fader 3", "mdi:tune-vertical"),
    GoXLRMapItem("D", "Fader 4", "mdi:tune-vertical"),
    GoXLRMapItem("Bleep", "Bleep", "mdi:cancel"),
    GoXLRMapItem("Cough", "Cough", "mdi:microphone-off"),
    GoXLRMapItem("Fader1Mute", "Fader 1 Mute", "mdi:volume-off"),
    GoXLRMapItem("Fader2Mute", "Fader 2 Mute", "mdi:volume-off"),
    GoXLRMapItem("Fader3Mute", "Fader 3 Mute", "mdi:volume-off"),
    GoXLRMapItem("Fader4Mute", "Fader 4 Mute", "mdi:volume-off"),
    GoXLRMapItem("EffectFx", "Effect FX", "mdi:magic-staff"),
    GoXLRMapItem("EffectMegaphone", "Effect Megaphone", "mdi:bullhorn"),
    GoXLRMapItem("EffectRobot", "Effect Robot", "mdi:robot"),
    GoXLRMapItem("EffectHardTune", "Effect Hard Tune", "mdi:music-note-eighth-dotted"),
    GoXLRMapItem("EffectSelect1", "Effect Select 1"),
    GoXLRMapItem("EffectSelect2", "Effect Select 2"),
    GoXLRMapItem("EffectSelect3", "Effect Select 3"),
    GoXLRMapItem("EffectSelect4", "Effect Select 4"),
    GoXLRMapItem("EffectSelect5", "Effect Select 5"),
    GoXLRMapItem("EffectSelect6", "Effect Select 6"),
    GoXLRMapItem("SamplerSelectA", "Sampler Select A"),
    GoXLRMapItem("SamplerSelectB", "Sampler Select B"),
    GoXLRMapItem("SamplerSelectC", "Sampler Select C"),
    GoXLRMapItem("SamplerTopLeft", "Sampler Top Left"),
    GoXLRMapItem("SamplerTopRight", "Sampler Top Right"),
    GoXLRMapItem("SamplerBottomLeft", "Sampler Bottom Left"),
    GoXLRMapItem("SamplerBottomRight", "Sampler Bottom Right"),
    GoXLRMapItem("SamplerClear", "Sampler Clear"),
):
    _register_map_item(NAME_MAP, map_item)


def get_map_item(key: Any) -> GoXLRMapItem | None:
    """Return UI metadata for a GoXLR item key."""
    raw = str(getattr(key, "value", key))
    return NAME_MAP.get(raw) or NAME_MAP.get(normalize_key(raw))


def resolve_enum(enum_cls: type[EnumT], value: Any) -> EnumT | None:
    """Resolve a GoXLR enum member from a normalized or raw string."""
    raw = str(getattr(value, "value", value))
    normalized = normalize_key(raw)

    for member in enum_cls:
        candidates = {
            member.name,
            str(member.value),
            normalize_key(member.name),
            normalize_key(str(member.value)),
        }
        if raw in candidates or normalized in candidates:
            return member

    return None


def resolve_button(value: Any) -> Button | None:
    """Resolve a GoXLR button enum."""
    return resolve_enum(Button, value)


def resolve_channel(value: Any) -> ChannelName | None:
    """Resolve a GoXLR channel enum."""
    return resolve_enum(ChannelName, value)


def resolve_input(value: Any) -> InputDevice | str | None:
    """Resolve a GoXLR routing input enum or preserve the raw value."""
    resolved = resolve_enum(InputDevice, value)
    if resolved is not None:
        return resolved

    raw = getattr(value, "value", value)
    return str(raw) if raw is not None else None


def resolve_output(value: Any) -> OutputDevice | str | None:
    """Resolve a GoXLR routing output enum or preserve the raw value."""
    resolved = resolve_enum(OutputDevice, value)
    if resolved is not None:
        return resolved

    raw = getattr(value, "value", value)
    return str(raw) if raw is not None else None


def resolve_fader(value: Any) -> FaderName | None:
    """Resolve a GoXLR fader enum."""
    return resolve_enum(FaderName, value)


def get_goxlr_attr(obj: Any, name: str, default: Any = None) -> Any:
    """Get an attribute or dict key using GoXLR naming variations."""
    base_name = name.removesuffix("_")
    candidates = [
        name,
        base_name,
        normalize_key(name),
        normalize_key(base_name),
        name.lower(),
        base_name.lower(),
        name.upper(),
        base_name.upper(),
        name.capitalize(),
        base_name.capitalize(),
        name.title(),
        base_name.title(),
    ]

    if isinstance(obj, dict):
        for candidate in candidates:
            if candidate in obj:
                return obj[candidate]

        lowered = {str(key).lower(): value for key, value in obj.items()}
        for candidate in candidates:
            if candidate.lower() in lowered:
                return lowered[candidate.lower()]

        normalized = {normalize_key(str(key)): value for key, value in obj.items()}
        for candidate in candidates:
            normalized_candidate = normalize_key(str(candidate))
            if normalized_candidate in normalized:
                return normalized[normalized_candidate]

        return default

    for candidate in candidates:
        if hasattr(obj, candidate):
            return getattr(obj, candidate)

    attrs = getattr(obj, "__dict__", {})
    lowered = {str(key).lower(): value for key, value in attrs.items()}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]

    normalized = {normalize_key(str(key)): value for key, value in attrs.items()}
    for candidate in candidates:
        normalized_candidate = normalize_key(str(candidate))
        if normalized_candidate in normalized:
            return normalized[normalized_candidate]

    return default


def get_goxlr_keys(obj: Any) -> list[str]:
    """Return normalized keys from a GoXLR object or dict."""
    if isinstance(obj, dict):
        keys = obj.keys()
    else:
        keys = getattr(obj, "__dict__", {}).keys()

    return [normalize_key(str(key)) for key in keys if not str(key).startswith("_")]


def get_volume_percentage(data: Any, key: str) -> float | None:
    """Return the volume percentage for a GoXLR channel."""
    volume = get_goxlr_attr(get_goxlr_attr(data.levels, "volumes"), key)
    if volume is None:
        return None

    return max(0.0, min(100.0, float(volume) / 255 * 100))


def extract_mixer_from_status(status: Any) -> Any | None:
    """Extract the first mixer from a GoXLR status payload."""
    payload = getattr(status, "data", status)

    if isinstance(payload, dict):
        payload = payload.get("Status", payload.get("status", payload))
        mixers = payload.get("mixers") if isinstance(payload, dict) else None
        if isinstance(mixers, dict) and mixers:
            return next(iter(mixers.values()))

    mixers = getattr(payload, "mixers", None)
    if isinstance(mixers, dict) and mixers:
        return next(iter(mixers.values()))

    return None


class HomeAssistantWebSocketTransport(WebSocketTransport):
    """GoXLR websocket transport that reuses Home Assistant's shared HTTP client."""

    def __init__(
        self, *args: Any, http_client: httpx.AsyncClient, **kwargs: Any
    ) -> None:
        """Initialize the transport with a shared HTTPX client."""
        super().__init__(*args, **kwargs)
        self._shared_http_client = http_client

    async def connect(self) -> None:
        """Connect without creating a new HTTPX client in the event loop."""
        self._stopping = False
        self._http_client = self._shared_http_client
        await self._do_connect()
        self._listener_task = asyncio.create_task(
            self._listen_loop(), name="goxlr-ws-listener"
        )

    async def disconnect(self) -> None:
        """Disconnect without closing Home Assistant's shared client."""
        self._stopping = True
        if self._listener_task is not None:
            self._listener_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listener_task
            self._listener_task = None
        await self._close_ws()
        self._http_client = None


async def close_connection(client: GoXLRClient) -> None:
    """Close the GoXLR client connection."""
    with contextlib.suppress(Exception):
        await client.__aexit__(None, None, None)


async def setup_connection(
    _hass: HomeAssistant,
    data: dict[str, Any],
    *,
    on_state_update: Any = None,
    on_disconnect: Any = None,
) -> GoXLRClient:
    """Set up a GoXLR websocket connection."""
    host = str(data["host"]).strip()
    port = int(data["port"])
    websocket_url = f"ws://{host}:{port}/api/websocket"

    _LOGGER.debug("Connecting to GoXLR Utility via websocket at %s", websocket_url)

    transport = HomeAssistantWebSocketTransport(
        url=websocket_url,
        http_client=get_async_client(_hass),
    )

    client = GoXLRClient(
        transport,
        on_state_update=on_state_update,
        on_disconnect=on_disconnect,
    )

    try:
        async with asyncio.timeout(10):
            await client.__aenter__()
            status = await client.get_status()
    except TimeoutError as exception:
        _LOGGER.warning(
            "Timed out connecting to GoXLR Utility via websocket at %s",
            websocket_url,
        )
        with contextlib.suppress(Exception):
            await client.__aexit__(None, None, None)
        raise CannotConnect(f"Timed out connecting to {host}:{port}") from exception
    except CONNECTION_ERRORS as exception:
        _LOGGER.warning(
            "Connection error while connecting to GoXLR Utility via websocket at %s: %r",
            websocket_url,
            exception,
        )
        if host in {"127.0.0.1", "localhost"}:
            _LOGGER.warning(
                "GoXLR host '%s' points to the local container. If Home Assistant is "
                "running in Docker or a devcontainer, use the host machine IP instead",
                host,
            )
        with contextlib.suppress(Exception):
            await client.__aexit__(None, None, None)
        raise CannotConnect(f"Cannot connect to {host}:{port}") from exception
    except Exception as exception:
        _LOGGER.exception(
            "Unexpected error while connecting to GoXLR Utility via websocket at %s",
            websocket_url,
        )
        with contextlib.suppress(Exception):
            await client.__aexit__(None, None, None)
        raise CannotConnect(
            f"Unexpected error connecting to {host}:{port}"
        ) from exception

    if extract_mixer_from_status(status) is None:
        _LOGGER.warning(
            "Connected to GoXLR Utility at %s:%s but no mixer was reported",
            host,
            port,
        )
        with contextlib.suppress(Exception):
            await client.__aexit__(None, None, None)
        raise CannotConnect(f"No mixer found at {host}:{port}")

    return client


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
