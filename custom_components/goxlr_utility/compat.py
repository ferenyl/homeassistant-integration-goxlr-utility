"""Compatibility helpers for the GoXLR Utility integration."""

from __future__ import annotations

import asyncio
from dataclasses import fields, is_dataclass
import logging
import sys
from typing import Any, get_args, get_origin, get_type_hints


def _coerce_value(annotation: Any, value: Any) -> Any:
    """Coerce a value into the requested dataclass annotation."""
    if value is None:
        return None

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin in (list, tuple) and args:
        return [_coerce_value(args[0], item) for item in value]

    if origin is dict and len(args) == 2:
        return {key: _coerce_value(args[1], item) for key, item in value.items()}

    if args:
        non_none_args = [arg for arg in args if arg is not type(None)]
        for arg in non_none_args:
            coerced = _coerce_value(arg, value)
            if coerced is not value or is_dataclass(arg):
                return coerced

    if isinstance(annotation, type) and is_dataclass(annotation) and isinstance(value, dict):
        return _build_dataclass(annotation, value)

    return value


def _build_dataclass(model_cls: type, payload: dict[str, Any]) -> Any:
    """Build a dataclass instance from API payload data."""
    type_hints = get_type_hints(model_cls)
    kwargs: dict[str, Any] = {}

    for field_info in fields(model_cls):
        alias = field_info.metadata.get("alias", field_info.name)
        key = None
        if field_info.name in payload:
            key = field_info.name
        elif alias in payload:
            key = alias
        elif field_info.name.endswith("_") and field_info.name[:-1] in payload:
            key = field_info.name[:-1]

        if key is None:
            continue

        annotation = type_hints.get(field_info.name, field_info.type)
        kwargs[field_info.name] = _coerce_value(annotation, payload[key])

    return model_cls(**kwargs)


def apply_goxlrutilityapi_compat() -> None:
    """Patch goxlrutilityapi compatibility issues for Home Assistant."""
    try:
        from goxlrutilityapi.base import Base
        from goxlrutilityapi.models import DefaultBaseModel
    except ImportError:
        return

    extra_field = getattr(DefaultBaseModel, "__dataclass_fields__", {}).get("_extra")
    if extra_field is not None and sys.version_info >= (3, 14):
        extra_field.init = False
        extra_field.kw_only = True

    try:
        from goxlrutilityapi.const import (
            ACCENT,
            COMMAND_TYPE_LOAD_PROFILE,
            COMMAND_TYPE_LOAD_PROFILE_COLOURS,
            COMMAND_TYPE_SET_BUTTON_COLOURS,
            COMMAND_TYPE_SET_FADER_COLOURS,
            COMMAND_TYPE_SET_MUTE_STATE,
            COMMAND_TYPE_SET_SIMPLE_COLOUR,
            COMMAND_TYPE_SET_VOLUME,
            KEY_TYPE,
            MUTED_STATE,
            REQUEST_TYPE_GET_STATUS,
            RESPONSE_TYPE_OK,
            RESPONSE_TYPE_PATCH,
            RESPONSE_TYPE_STATUS,
            UNMUTED_STATE,
        )
        from goxlrutilityapi.exceptions import BadMessageException, ConnectionErrorException
        import goxlrutilityapi.helpers as helpers_module
        from goxlrutilityapi.models.patch import Patch
        from goxlrutilityapi.models.status import Mixer
        from goxlrutilityapi.websocket_client import WebsocketClient
    except ImportError:
        return

    if getattr(WebsocketClient, "__ha_compat_patched__", False):
        return

    def _compat_base_init(
        self,
        id: str | None = None,
        jsonrpc: str = "2.0",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the compatibility-patched base model."""
        self.id = "" if id is None else str(id)
        self.jsonrpc = jsonrpc
        self.metadata = metadata
        name = f"{self.__module__}.{self.__class__.__name__}"
        self._logger = logging.getLogger(name)
        self._logger.debug("%s __init__", name)

    Base.__init__ = _compat_base_init

    class CompatResponse:
        """Compatibility response object exposing type and data attributes."""

        def __init__(self, message: dict[str, Any]) -> None:
            self.id = message.get("id")
            self.type = message.get("type") or message.get("status")
            self.data = message.get("data", message.get("result"))
            self.error = message.get("error")
            self.jsonrpc = message.get("jsonrpc", "2.0")

            if self.type == RESPONSE_TYPE_PATCH and isinstance(self.data, dict):
                self.data = Patch(**self.data)

    def _normalize_mixer_from_status(status: Any) -> Any:
        """Return the first mixer from a status-like payload."""
        payload = getattr(status, "data", status)
        if isinstance(payload, dict) and "Status" in payload:
            payload = payload["Status"]

        if isinstance(payload, dict):
            mixers = payload.get("mixers")
            if isinstance(mixers, dict):
                mixer = next(iter(mixers.values()), None)
                if isinstance(mixer, dict):
                    try:
                        return _build_dataclass(Mixer, mixer)
                    except TypeError:
                        return None
                return mixer

        mixers = getattr(payload, "mixers", None)
        if isinstance(mixers, dict):
            return next(iter(mixers.values()), None)

        return None

    def _get_attribute_names_from_patch(data: Mixer, patch: Patch) -> list[str]:
        """Get attribute names from a patch using dataclass metadata aliases."""
        paths = patch.path.split("/")
        if len(paths) <= 3 or paths[1] != "mixers":
            raise ValueError("Unused patch received")

        current_attribute: Any = data
        attribute_names: list[str] = []

        for path in paths[3:]:
            resolved_name = path
            if is_dataclass(current_attribute):
                for field_info in fields(current_attribute):
                    alias = field_info.metadata.get("alias", field_info.name)
                    if alias == path or field_info.name == path:
                        resolved_name = field_info.name
                        break

            current_attribute = getattr(current_attribute, resolved_name)
            attribute_names.append(resolved_name)

        return attribute_names

    async def _compat_send_message(
        self,
        request: dict[str, Any],
        wait_for_response: bool = True,
        response_type: str | None = None,
    ) -> CompatResponse:
        """Send a message using the payload shape expected by the daemon."""
        if not self.connected:
            raise ConnectionErrorException

        self._message_id += 1
        request_id = self._message_id
        payload = dict(request)
        payload["id"] = request_id

        if wait_for_response:
            self._message_events[request_id] = asyncio.Event()

        await self._websocket.send_json(payload)

        if not wait_for_response:
            return CompatResponse({"id": request_id, "type": RESPONSE_TYPE_OK, "data": None})

        try:
            await self._message_events[request_id].wait()
        except asyncio.TimeoutError as error:
            raise ConnectionErrorException from error

        response = self._message_responses.pop(request_id)
        self._message_events.pop(request_id, None)

        if response_type is not None and response.type != response_type:
            if not (
                response_type == RESPONSE_TYPE_STATUS
                and isinstance(response.data, dict)
                and (
                    "Status" in response.data
                    or "status" in response.data
                    or "mixers" in response.data
                )
            ):
                raise BadMessageException(f"Expected {response_type}, got {response.type}")

        return response

    async def _compat_get_status(self) -> Any:
        """Get status from GoXLR Utility."""
        response = await self._send_message({"data": REQUEST_TYPE_GET_STATUS})
        if isinstance(response.data, dict):
            return response.data.get("Status", response.data.get("status", response.data))
        return response.data

    async def _compat_set_accent_color(self, color: str) -> None:
        await self._send_message(
            {"data": {KEY_TYPE: COMMAND_TYPE_SET_SIMPLE_COLOUR, ACCENT: color}},
            response_type=RESPONSE_TYPE_OK,
        )

    async def _compat_set_button_color(self, name: str, color_one: str, color_two: str) -> None:
        await self._send_message(
            {
                "data": {
                    KEY_TYPE: COMMAND_TYPE_SET_BUTTON_COLOURS,
                    name: {"colour_one": color_one, "colour_two": color_two},
                }
            },
            response_type=RESPONSE_TYPE_OK,
        )

    async def _compat_set_fader_color(self, name: str, color_top: str, color_bottom: str) -> None:
        await self._send_message(
            {
                "data": {
                    KEY_TYPE: COMMAND_TYPE_SET_FADER_COLOURS,
                    name: {"colour_one": color_top, "colour_two": color_bottom},
                }
            },
            response_type=RESPONSE_TYPE_OK,
        )

    async def _compat_set_muted(self, channel: str, muted: bool) -> None:
        await self._send_message(
            {
                "data": {
                    KEY_TYPE: COMMAND_TYPE_SET_MUTE_STATE,
                    channel: MUTED_STATE if muted else UNMUTED_STATE,
                }
            },
            response_type=RESPONSE_TYPE_OK,
        )

    async def _compat_set_volume(self, channel: str, volume: int) -> None:
        await self._send_message(
            {"data": {KEY_TYPE: COMMAND_TYPE_SET_VOLUME, channel: volume}},
            response_type=RESPONSE_TYPE_OK,
        )

    async def _compat_load_profile(self, profile: str) -> None:
        await self._send_message(
            {"data": {KEY_TYPE: COMMAND_TYPE_LOAD_PROFILE, "profile": profile}},
            response_type=RESPONSE_TYPE_OK,
        )

    async def _compat_load_profile_colours(self, profile: str) -> None:
        await self._send_message(
            {"data": {KEY_TYPE: COMMAND_TYPE_LOAD_PROFILE_COLOURS, "profile": profile}},
            response_type=RESPONSE_TYPE_OK,
        )

    async def _compat_listen(self, patch_callback=None) -> None:
        """Listen for messages with compatibility response parsing."""

        async def _message_callback(message: dict[str, Any]) -> None:
            try:
                response = CompatResponse(message)
                response_id = response.id
                if isinstance(response_id, str) and response_id.isdigit():
                    response_id = int(response_id)

                if response_id in self._message_events:
                    self._message_responses[response_id] = response
                    self._message_events[response_id].set()
                    return

                if response.type in (RESPONSE_TYPE_PATCH, RESPONSE_TYPE_STATUS) and patch_callback is not None:
                    await patch_callback(response)
            except (TypeError, ValueError) as error:
                raise BadMessageException from error

        await self._listen_for_messages(_message_callback)

    helpers_module.get_mixer_from_status = _normalize_mixer_from_status
    helpers_module.get_attribute_names_from_patch = _get_attribute_names_from_patch

    WebsocketClient._send_message = _compat_send_message
    WebsocketClient.get_status = _compat_get_status
    WebsocketClient.set_accent_color = _compat_set_accent_color
    WebsocketClient.set_button_color = _compat_set_button_color
    WebsocketClient.set_fader_color = _compat_set_fader_color
    WebsocketClient.set_muted = _compat_set_muted
    WebsocketClient.set_volume = _compat_set_volume
    WebsocketClient.load_profile = _compat_load_profile
    WebsocketClient.load_profile_colours = _compat_load_profile_colours
    WebsocketClient.listen = _compat_listen
    WebsocketClient.__ha_compat_patched__ = True


apply_goxlrutilityapi_compat()
