"""Helper for GoXLR Utility integration."""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

from . import compat  # noqa: F401

import async_timeout
from goxlrutilityapi.websocket_client import WebsocketClient

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONNECTION_ERRORS

_LOGGER = logging.getLogger(__name__)


def _to_namespace(value: Any) -> Any:
    """Convert nested dict payloads to attribute-accessible objects."""
    if isinstance(value, dict):
        return SimpleNamespace(**{key: _to_namespace(item) for key, item in value.items()})
    if isinstance(value, list):
        return [_to_namespace(item) for item in value]
    return value


def extract_mixer_from_status(status: Any) -> Any | None:
    """Extract the first mixer from a GoXLR status payload."""
    payload = getattr(status, "data", status)

    if isinstance(payload, dict):
        payload = payload.get("Status", payload.get("status", payload))
        mixers = payload.get("mixers") if isinstance(payload, dict) else None
        if isinstance(mixers, dict) and mixers:
            return _to_namespace(next(iter(mixers.values())))

    mixers = getattr(payload, "mixers", None)
    if isinstance(mixers, dict) and mixers:
        mixer = next(iter(mixers.values()))
        return _to_namespace(mixer)

    return None


async def setup_connection(
    hass: HomeAssistant,
    data: dict[str, Any],
) -> WebsocketClient:
    """Set up connection to GoXLR Utility."""
    async with async_timeout.timeout(10):
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
