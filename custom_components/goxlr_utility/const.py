"""Constants for the GoXLR Utility integration."""

from typing import Final

from goxlrutil_api.exceptions import ConnectionError as GoXLRConnectionError

DOMAIN: Final[str] = "goxlr_utility"
DEFAULT_PORT: Final[int] = 14564

CONNECTION_ERRORS: Final = (
    GoXLRConnectionError,
    ConnectionError,
    OSError,
    TimeoutError,
)
