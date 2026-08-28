"""Public CLI exit-code allocation."""

from enum import IntEnum


class ExitCode(IntEnum):
    """Stable process outcomes for Galley commands."""

    COMPLETED = 0
    INVOCATION_ERROR = 2
    REFUSED = 3
    INTERNAL_ERROR = 4
    DELIVERY_UNCONFIRMED = 5
