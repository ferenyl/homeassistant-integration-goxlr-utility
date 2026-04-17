"""Constants for the GoXLR Utility integration."""
from typing import Final

from . import compat  # noqa: F401

from goxlrutilityapi.exceptions import (
    ConnectionClosedException,
    ConnectionErrorException,
)

DOMAIN: Final[str] = "goxlr_utility"

CONNECTION_ERRORS: Final = (
    ConnectionClosedException,
    ConnectionErrorException,
    ConnectionResetError,
)
