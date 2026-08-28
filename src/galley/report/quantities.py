"""Write and read the wrapped quantities every number in a Report travels as.

Each quantity has a basis — `measured`, `projected` with its relation, or `reported` — so a Report
never carries a bare number whose provenance a reader must guess.
The readers mirror the writers: they unwrap without inventing, returning nothing where a
command had no instrument.
"""

from galley.json_reading import mapping


def quantity(value: int, unit: str) -> dict[str, object]:
    """Wrap one directly measured count as a canonical Report quantity."""

    return {"basis": "measured", "unit": unit, "value": value}


def projected(value: int, unit: str, relation: str) -> dict[str, object]:
    """Wrap one quantity Galley infers about a future artifact, with its relation to it.

    The relation matters because a bound is actionable where a bare estimate is not: a lower
    bound already above a limit proves the limit is broken, and one below it proves nothing.
    """

    return {"basis": "projected", "relation": relation, "unit": unit, "value": value}


def reported(value: int, unit: str | None = None) -> dict[str, object]:
    """Wrap one quantity Galley did not take itself as a canonical Report quantity."""

    fact: dict[str, object] = {"basis": "reported", "value": value}
    if unit is not None:
        fact["unit"] = unit
    return fact


def group(facts: dict[str, object], key: str) -> dict[str, object]:
    """Read one nested fact object, which is absent wherever a command had no instrument."""

    return mapping(facts.get(key))


def amount(facts: dict[str, object], key: str) -> object:
    """Read one wrapped quantity's value, since every number in a Report is a wrapped one."""

    return group(facts, key).get("value")


def nested_amount(facts: dict[str, object], name: str, key: str) -> object:
    """Read one wrapped quantity's value from a nested fact object."""

    return amount(group(facts, name), key)
