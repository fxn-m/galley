"""Read the release-scope data Galley ships beside its code.

Modelled Set membership, Pandoc's AST vocabulary and the source kinds Galley reads are facts
about a Galley release, not about a Device Profile or one document. They live in validated data
so a name cannot drift without a gate failing.
"""

from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import cast

import yaml

from galley.json_reading import sequence, text

MODELLED_SET = "modelled-set.yaml"
PANDOC_AST = "pandoc-ast.yaml"
SOURCE_KINDS = "source-kinds.yaml"
XHTML_ATTRIBUTES = "xhtml-attributes.yaml"
# Where each constructor Pandoc gives an `Attr` keeps it. This is the AST's shape rather than the
# output format's, so it stays in code beside the reader that needs it and out of the data file.
ATTR_POSITION = {
    "Header": 1,
    "CodeBlock": 0,
    "Code": 0,
    "Div": 0,
    "Figure": 0,
    "Image": 0,
    "Link": 0,
    "Span": 0,
    "Table": 0,
}


@cache
def release_document(name: str) -> dict[str, object]:
    """Load one packaged release-scope data file."""

    raw = cast(
        object, yaml.safe_load(files("galley.data").joinpath(name).read_text(encoding="utf-8"))
    )
    return cast(dict[str, object], raw) if isinstance(raw, dict) else {}


@cache
def names(name: str, key: str) -> frozenset[str]:
    """Return one release-scope list of constructor names."""

    return frozenset(
        value for entry in sequence(release_document(name).get(key)) if (value := text(entry))
    )


def pinned_pandoc_version() -> str:
    """Name the exact Pandoc release Galley's AST vocabulary was validated against."""

    return text(release_document(PANDOC_AST).get("pandoc_version")) or ""


def modelled_set_schema() -> str:
    """Name the exact Modelled Set that judged a document's constructors."""

    return text(release_document(MODELLED_SET).get("schema")) or ""


class ReleaseDataError(ValueError):
    """Release-scope data disagrees with the code that reads it, which no run may proceed on."""


@dataclass(frozen=True)
class ElementRule:
    """What one Pandoc constructor becomes, and what that element admits beyond the global set."""

    element: str
    position: int
    attributes: frozenset[str]


@cache
def attribute_rules(
    name: str,
) -> tuple[frozenset[str], tuple[str, ...], dict[str, ElementRule]]:
    """Read what an EPUB3 content document admits: globally, by prefix, and element by element."""

    document = release_document(name)
    prefixes = tuple(
        value for entry in sequence(document.get("global_prefixes")) if (value := text(entry))
    )
    stated = {
        text(cast(dict[str, object], raw).get("constructor")) or "": cast(dict[str, object], raw)
        for raw in sequence(document.get("elements"))
    }
    if set(stated) != set(ATTR_POSITION):
        raise ReleaseDataError(
            f"{name} names {sorted(set(stated) ^ set(ATTR_POSITION))}, "
            "which no `Attr` position is stated for, or the other way about"
        )
    elements = {
        constructor: ElementRule(
            element=text(entry.get("element")) or "",
            position=ATTR_POSITION[constructor],
            attributes=frozenset(
                value for item in sequence(entry.get("attributes")) if (value := text(item))
            ),
        )
        for constructor, entry in stated.items()
    }
    return names(name, "global"), prefixes, elements
