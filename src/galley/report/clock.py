"""The one UTC and monotonic clock a Report's timing facts come from.

Both sources are injectable so a test can drive time through the public seam instead of
monkeypatching module privates; the defaults are the real clocks, and nothing else in the
package reads time any other way.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter_ns


def _system_utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Clock:
    """Injectable UTC and monotonic time sources, defaulting to the system clocks."""

    utc_now: Callable[[], datetime] = field(default=_system_utc_now)
    monotonic_ns: Callable[[], int] = field(default=perf_counter_ns)


def timestamp(value: datetime) -> str:
    """Render one UTC moment in the canonical Report timestamp shape."""

    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")
