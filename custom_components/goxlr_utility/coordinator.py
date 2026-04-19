"""Coordinator for GoXLR Utility integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from goxlrutil_api import GoXLRClient
from goxlrutil_api.protocol.responses import DaemonStatus, MixerStatus

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .helper import (
    CannotConnect,
    close_connection,
    extract_mixer_from_status,
    setup_connection,
)


class GoXLRUtilityDataUpdateCoordinator(DataUpdateCoordinator[MixerStatus]):
    """Class to manage fetching GoXLR Utility data from single endpoint."""

    def __init__(
        self,
        hass: HomeAssistant,
        LOGGER: logging.Logger,
        *,
        entry: ConfigEntry,
    ) -> None:
        """Initialize global GoXLR Utility data updater."""
        self._entry_data: dict[str, Any] = entry.data.copy()
        self.client: GoXLRClient | None = None
        self.title = entry.title
        self.unsub: CALLBACK_TYPE | None = None

        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=10),
        )

    @property
    def is_ready(self) -> bool:
        """Return if the data is ready."""
        return self.data is not None

    @property
    def serial_number(self) -> str | None:
        """Return the connected mixer serial number."""
        if self.data is None:
            return None
        return getattr(self.data.hardware, "serial_number", None)

    async def _handle_state_update(self, status: DaemonStatus) -> None:
        """Update Home Assistant when the GoXLR state cache changes."""
        mixer = extract_mixer_from_status(status)
        if mixer is None:
            return

        self.last_update_success = True
        self.async_set_updated_data(mixer)

    async def _handle_disconnect(self) -> None:
        """Mark entities unavailable when the websocket disconnects."""
        self.logger.debug("Websocket disconnected for %s", self.title)
        self.last_update_success = False
        self.async_update_listeners()

    async def setup(self) -> None:
        """Set up connection to the GoXLR websocket."""
        if self.client is not None:
            return

        self.client = await setup_connection(
            self.hass,
            self._entry_data.copy(),
            on_state_update=self._handle_state_update,
            on_disconnect=self._handle_disconnect,
        )

        async def cleanup(_: Event) -> None:
            """Disconnect and cleanup items."""
            await self.cleanup()

        self.unsub = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP,
            cleanup,
        )

    async def cleanup(self) -> None:
        """Disconnect and cleanup items."""
        if self.unsub is not None:
            self.unsub()
            self.unsub = None

        if self.client is not None:
            client = self.client
            self.client = None
            await close_connection(client)

    async def _get_mixer(self) -> MixerStatus:
        """Get mixer from GoXLR Utility."""
        if self.client is None:
            raise ConfigEntryNotReady("Websocket not connected")

        status = await self.client.get_status()
        mixer = extract_mixer_from_status(status)
        if mixer is None:
            raise ConfigEntryNotReady("No mixer found")
        return mixer

    async def _async_update_data(self) -> MixerStatus:
        """Update GoXLR Utility data from WebSocket."""
        if self.client is None:
            try:
                await self.setup()
            except (TimeoutError, CannotConnect) as exception:
                self.logger.info("Could not connect to GoXLR Utility: %s", exception)
                raise ConfigEntryNotReady(exception) from exception

        mixer = await self._get_mixer()
        self.logger.debug("Data updated: %s", mixer)
        return mixer
