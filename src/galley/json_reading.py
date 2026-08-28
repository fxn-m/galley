"""Read untyped JSON and YAML values defensively, without inventing facts about them."""

from typing import cast


def integer(value: object) -> int | None:
    """Return a true integer, never a boolean standing in for one."""

    return value if isinstance(value, int) and not isinstance(value, bool) else None


def text(value: object) -> str | None:
    """Return a string value, or None when the document offered something else."""

    return value if isinstance(value, str) else None


def mapping(value: object) -> dict[str, object]:
    """Return a mapping, or an empty one when the document offered something else."""

    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def sequence(value: object) -> list[object]:
    """Return a list, or an empty one when the document offered something else."""

    return cast(list[object], value) if isinstance(value, list) else []
