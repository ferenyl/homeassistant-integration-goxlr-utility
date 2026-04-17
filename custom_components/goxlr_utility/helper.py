"""Helper for GoXLR Utility integration."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from types import SimpleNamespace
from typing import Any

from goxlrutilityapi.websocket_client import WebsocketClient

try:
    from goxlrutilityapi.models.status import Mixer as GoXLRMixer
except ImportError:
    GoXLRMixer = None

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import compat
from .const import CONNECTION_ERRORS

_LOGGER = logging.getLogger(__name__)


def _to_namespace(value: Any) -> Any:
    """Convert nested dict payloads to attribute-accessible objects."""
    if isinstance(value, dict):
        return SimpleNamespace(
            **{
                compat.normalize_key(str(key)): _to_namespace(item)
                for key, item in value.items()
            }
        )
    if isinstance(value, list):
        return [_to_namespace(item) for item in value]
    return value


def get_goxlr_attr(obj: Any, name: str, default: Any = None) -> Any:
    """Get an attribute or dict key using GoXLR naming variations."""
    base_name = name.removesuffix("_")
    candidates = [
        name,
        base_name,
        compat.normalize_key(name),
        compat.normalize_key(base_name),
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
        return default

    for candidate in candidates:
        if hasattr(obj, candidate):
            return getattr(obj, candidate)

    attrs = getattr(obj, "__dict__", {})
    lowered = {str(key).lower(): value for key, value in attrs.items()}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]

    return default


def get_goxlr_keys(obj: Any) -> list[str]:
    """Return normalized keys from a GoXLR object or dict."""
    if isinstance(obj, dict):
        keys = obj.keys()
    else:
        keys = getattr(obj, "__dict__", {}).keys()

    return [
        compat.normalize_key(str(key)) for key in keys if not str(key).startswith("_")
    ]


def _coerce_mixer(mixer: Any) -> Any:
    """Convert a mixer payload to a model or namespace."""
    if not isinstance(mixer, dict):
        return mixer

    if GoXLRMixer is not None:
        with contextlib.suppress(TypeError, ValueError):
            return compat.build_dataclass(GoXLRMixer, mixer)

    return _to_namespace(mixer)


def extract_mixer_from_status(status: Any) -> Any | None:
    """Extract the first mixer from a GoXLR status payload."""
    payload = getattr(status, "data", status)

    if isinstance(payload, dict):
        payload = payload.get("Status", payload.get("status", payload))
        mixers = payload.get("mixers") if isinstance(payload, dict) else None
        if isinstance(mixers, dict) and mixers:
            return _coerce_mixer(next(iter(mixers.values())))

    mixers = getattr(payload, "mixers", None)
    if isinstance(mixers, dict) and mixers:
        return _coerce_mixer(next(iter(mixers.values())))

    return None


async def close_connection(websocket_client: WebsocketClient) -> None:
    """Close the websocket without closing Home Assistant's shared session."""
    websocket = getattr(websocket_client, "_websocket", None)
    if websocket is not None:
        with contextlib.suppress(Exception):
            await websocket.close()
        setattr(websocket_client, "_websocket", None)

    setattr(websocket_client, "_session", None)


async def setup_connection(
    hass: HomeAssistant,
    data: dict[str, Any],
) -> WebsocketClient:
    """Set up connection to GoXLR Utility."""
    async with asyncio.timeout(10):
        websocket_client = WebsocketClient()
        try:
            await websocket_client.connect(
                data["host"],
                data["port"],
                async_get_clientsession(hass),
            )
        except CONNECTION_ERRORS as exception:
            _LOGGER.warning("Connection error: %s", exception)
            raise CannotConnect from exception

        return websocket_client


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
