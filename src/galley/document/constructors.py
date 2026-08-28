"""Count Pandoc constructors and name the ones outside the Modelled Set.

These are the purest of the five fact categories: a function of the AST and the Modelled Set
alone, with no profile input. Unsupported Content is carried through to output and reported,
never dropped and never a reason to refuse.
"""

from dataclasses import dataclass, field

from galley.json_reading import mapping, sequence, text
from galley.release_data import (
    MODELLED_SET,
    PANDOC_AST,
    modelled_set_schema,
    names,
)
from galley.report.quantities import quantity

CARRIED_THROUGH = "carried-through"
BLOCKS = names(PANDOC_AST, "blocks")
INLINES = names(PANDOC_AST, "inlines")
NODES = BLOCKS | INLINES
# Every name Pandoc's own AST uses. A `t` outside this is a constructor Galley has never heard of.
KNOWN = NODES | names(PANDOC_AST, "other") | names(PANDOC_AST, "sub_types")
MODELLED = names(MODELLED_SET, "constructors")
# Locations are JSON Pointers into the native AST, which the Canonical Document nests under this
# key. A consumer holding `canonical-document.json` prepends it; one holding the AST does not.
LOCATION_BASE = "pandoc"
ROOTS = ("blocks", "meta")


@dataclass
class Survey:
    """Every constructor one AST carries, by name and by location."""

    locations: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    unrecognised: set[str] = field(default_factory=set[str])

    @property
    def carried_through(self) -> list[str]:
        """Name everything outside the Modelled Set, in stable order."""

        return sorted(set(self.locations) - MODELLED)


def constructor_facts(ast: dict[str, object]) -> dict[str, object]:
    """Describe the AST's constructors and its Unsupported Content as Canonical Document facts."""

    survey = _survey(ast)
    return {
        "constructors": {
            name: quantity(len(locations), "nodes")
            for name, locations in sorted(survey.locations.items())
        },
        "location_base": LOCATION_BASE,
        "modelled_set": modelled_set_schema(),
        "unsupported": [_record(name, survey) for name in survey.carried_through],
    }


def constructor_locations(ast: dict[str, object]) -> dict[str, list[str]]:
    """Every JSON Pointer at which each constructor occurs — the survey the facts are read from.

    An observation that fires wherever a construct appears needs this survey and nothing more, so
    it reads the one definition of where a node can sit rather than walking the AST again beside
    it. Metadata is surveyed too, for the reason `_survey` gives.
    """

    return _survey(ast).locations


def _survey(ast: dict[str, object]) -> Survey:
    """Record where every constructor sits, in document order.

    Both the body and the document's metadata are surveyed, because Pandoc's writers put `meta`
    on the page too — a struck-through title reaches the book exactly as a struck-through
    paragraph does.
    """

    survey = Survey()
    for root in ROOTS:
        _walk(ast.get(root), f"/{root}", survey)
    return survey


def _record(name: str, survey: Survey) -> dict[str, object]:
    locations = survey.locations[name]
    return {
        "constructor": name,
        "count": quantity(len(locations), "occurrences"),
        "disposition": CARRIED_THROUGH,
        "in_modelled_set": False,
        "locations": locations,
        "recognised": name not in survey.unrecognised,
    }


def _walk(value: object, pointer: str, survey: Survey) -> None:
    """Descend every position, naming each node by its JSON Pointer into the native AST.

    A `t` value is a constructor when Pandoc's own vocabulary names it as a block or an inline;
    a sub-type tag such as `AlignDefault` is listed separately and is not content. A name in
    neither list is one Galley has never met, so it is reported rather than passed over.
    """

    items = sequence(value)
    if items:
        for index, item in enumerate(items):
            _walk(item, f"{pointer}/{index}", survey)
        return
    node = mapping(value)
    name = text(node.get("t"))
    if name is not None and name not in KNOWN:
        survey.unrecognised.add(name)
    if name is not None and (name in NODES or name in survey.unrecognised):
        survey.locations.setdefault(name, []).append(pointer)
    for key, child in node.items():
        _walk(child, f"{pointer}/{key}", survey)
