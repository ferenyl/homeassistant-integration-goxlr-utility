"""Config flow for GoXLR Utility integration."""

from __future__ import annotations

import logging
from typing import Any, Self

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DEFAULT_PORT, DOMAIN
from .helper import (
    CannotConnect,
    close_connection,
    extract_mixer_from_status,
    setup_connection,
)

_LOGGER = logging.getLogger(__name__)


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(
            CONF_PORT,
            default=DEFAULT_PORT,
        ): int,
    }
)


async def validate_input(
    hass: HomeAssistant,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    client = await setup_connection(hass, data)

    try:
        status = await client.get_status()
        mixer = extract_mixer_from_status(status)
        if mixer is None:
            raise CannotConnect("No mixer found")
    finally:
        await close_connection(client)

    identifier = getattr(mixer.hardware, "serial_number", None)
    manufacturer = (
        getattr(mixer.hardware.usb_device, "manufacturer_name", None) or "TC-Helicon"
    )
    product = getattr(mixer.hardware.usb_device, "product_name", None) or (
        f"GoXLR {getattr(getattr(mixer.hardware, 'device_type', None), 'value', '')}".strip()
    )

    if not identifier:
        raise CannotConnect("Incomplete mixer information received")

    return {
        "title": f"{manufacturer} - {product}",
        "identifier": identifier,
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for GoXLR Utility."""

    VERSION = 1

    def is_matching(self, other_flow: Self) -> bool:
        """Return True if another in-progress flow is for the same device."""
        return False

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except (TimeoutError, CannotConnect) as exception:
                _LOGGER.warning(
                    "Failed to connect to GoXLR Utility at %s:%s: %s",
                    user_input.get(CONF_HOST),
                    user_input.get(CONF_PORT),
                    exception,
                )
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info["identifier"])
                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
