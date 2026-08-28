"""Remove every actionable href a Device Profile does not want, on a private working copy.

The X4 profile keeps `href` only on a recognised Footnote Apparatus. The device lists every in-book
link in one sixteen-slot Footnotes surface and discards the rest silently, so a cross-reference
evicts a real note. The rule is categorical rather than density-triggered because the budget is
per rendered screen and Galley cannot compute rendered screens.

Nothing here decides device policy. Whether to strip at all is a Device Profile activation and
which links a device records is the profile's own counting rule. This module applies
both and states neither.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from galley.document.ast_reading import resolves_in_document
from galley.document.baseline import inline_text
from galley.document.link_kinds import (
    KINDS,
    STRIP_ACTIVATION,
    CountingRule,
    LinkKind,
    is_external,
    link_kind,
)
from galley.json_reading import sequence, text
from galley.profile.loading import activation_entry
from galley.report.quantities import quantity

LINK = "Link"
SPAN = "Span"
LINK_STRIPPING = "link-stripping"
# Pandoc's Attr is an identifier, a list of classes and a list of key-value pairs.
ATTRIBUTE_PARTS = 3

STRIP_INACTIVE = (
    "This Device Profile does not activate href stripping, so every link keeps its destination. "
    "The kinds are still counted, because what a profile declined to strip is a fact about the "
    "book it produced."
)
STRIP_NOTHING = (
    "This Device Profile strips hrefs outside the Footnote Apparatus, and the Canonical Document "
    "carries no link for the rule to act on. Nothing was removed because there was nothing to "
    "remove."
)
STRIP_APPLIED = (
    "Web and dead destinations were removed unconditionally and cross-references with them, "
    "because this document's Footnote Apparatus is recognised and the links outside it would "
    "occupy the navigation slots the apparatus needs. Every visible word was kept."
)
STRIP_INTERLOCKED = (
    "The safety interlock retained this document's cross-references. It carries in-book links "
    "and zero recognised notes, which is exactly the state in which a footnote reference is "
    "indistinguishable from a cross-reference, so removing them could destroy notes irreversibly. "
    "Web and dead destinations were still removed, since neither can be reached by this reader."
)


@dataclass(frozen=True)
class ClassifiedLink:
    """One `Link` inline, the kind the Device Profile makes of it, and what stripping did."""

    kind: LinkKind
    target: str
    text: str
    recorded: bool
    removed: bool


@dataclass(frozen=True)
class Stripping:
    """One stripping pass: the working copy it produced and every link it classified."""

    ast: dict[str, object]
    links: tuple[ClassifiedLink, ...]
    activated: bool
    apparatus: bool
    notes: int

    @property
    def removed(self) -> list[ClassifiedLink]:
        return [link for link in self.links if link.removed]

    @property
    def in_book(self) -> list[ClassifiedLink]:
        return [link for link in self.links if link.kind != "web-link"]

    @property
    def interlocked(self) -> bool:
        """Say whether the safety interlock is what retained this document's cross-references.

        It fires on a counted zero rather than on a threshold: a document carrying in-book links
        and no recognised note is one whose footnote references are indistinguishable from its
        cross-references, so stripping them would destroy notes irreversibly.
        """

        return self.activated and not self.apparatus and bool(self.in_book)


def strip_links(
    ast: dict[str, object],
    *,
    rule: CountingRule,
    identifiers: Sequence[str],
    notes: int,
    activated: bool,
) -> Stripping:
    """Classify every `Link` in one Canonical Document and remove unwanted hrefs.

    The recognised Footnote Apparatus is the counted `Note`. A document carrying none has no
    apparatus for a link to belong to, so no link is classified as part of one and the interlock
    retains what is left rather than guessing which cross-reference was really a note.
    """

    classified: list[ClassifiedLink] = []
    known = frozenset(identifiers)
    working = _value(
        ast,
        _Rules(rule=rule, known=known, apparatus=notes > 0, activated=activated),
        classified,
    )
    return Stripping(
        ast=cast(dict[str, object], working),
        links=tuple(classified),
        activated=activated,
        apparatus=notes > 0,
        notes=notes,
    )


def link_transform(profile: dict[str, object], stripping: Stripping) -> dict[str, object]:
    """State what href stripping removed, by Link Kind, and what the interlock retained."""

    entry = activation_entry(profile, STRIP_ACTIVATION)
    return {
        "name": LINK_STRIPPING,
        "fired": bool(stripping.removed),
        "activation": STRIP_ACTIVATION,
        "device_judged": entry.get("device_judged") is True,
        "justified_by": entry.get("justified_by"),
        "interlock": _interlock(stripping),
        "kinds": {kind: _kind_counts(stripping, kind) for kind in KINDS},
        "recorded": _counts([link for link in stripping.links if link.recorded]),
        "total": _counts(list(stripping.links)),
        "note": _strip_note(stripping),
    }


@dataclass(frozen=True)
class _Rules:
    """Everything one stripping pass needs to decide a link, gathered before the walk."""

    rule: CountingRule
    known: frozenset[str]
    apparatus: bool
    activated: bool


class _Spliced(list[object]):
    """Inlines that replace one unwrapped `Link` in the list that held it.

    A `Link` only ever sits in a list of inlines, so splicing its children into that list is
    always well formed and leaves no wrapper the source did not carry.
    """


def _value(value: object, rules: _Rules, classified: list[ClassifiedLink]) -> object:
    """Rebuild one AST value, replacing every `Link` this profile strips as the walk reaches it.

    The whole document is walked rather than a named set of containers, so a link inside a table
    cell, a definition list or a note body is reached by the same rule as one in a paragraph.
    """

    if isinstance(value, list):
        rebuilt: list[object] = []
        for item in cast(list[object], value):
            replacement = _value(item, rules, classified)
            if isinstance(replacement, _Spliced):
                rebuilt.extend(cast(list[object], replacement))
            else:
                rebuilt.append(replacement)
        return rebuilt
    if isinstance(value, dict):
        node = cast(dict[str, object], value)
        if text(node.get("t")) == LINK:
            return _link(node, rules, classified)
        return {key: _value(item, rules, classified) for key, item in node.items()}
    return value


def _link(node: dict[str, object], rules: _Rules, classified: list[ClassifiedLink]) -> object:
    """Classify one `Link`, then either keep it whole or replace it with its own visible text."""

    content = sequence(node.get("c"))
    attribute = _at(content, 0)
    inlines = cast(list[object], _value(sequence(_at(content, 1)), rules, classified))
    target = text(_at(sequence(_at(content, 2)), 0)) or ""
    visible = inline_text(sequence(_at(content, 1))).strip()
    external = is_external(target, rules.rule)
    resolves = not external and resolves_in_document(target, rules.known)
    # Two of the five Link Kinds cannot arise here, a fact about the Canonical Document rather
    # than a gap: notes carry no identifier for a link to point at, and note references are
    # created by the note conversion after this transform has run. A link merely *labelled* a
    # note reference is classified by where it actually points.
    kind = link_kind(external=external, resolves=resolves)
    removed = rules.activated and _removable(kind, rules)
    classified.append(
        ClassifiedLink(
            kind=kind,
            target=target,
            text=visible,
            recorded=not external and (bool(visible) or not rules.rule.requires_visible_text),
            removed=removed,
        )
    )
    if not removed:
        return {**node, "c": [attribute, inlines, _at(content, 2)]}
    return _unwrapped(attribute, inlines)


def _removable(kind: LinkKind, rules: _Rules) -> bool:
    """Say whether the profile rule removes one link's destination.

    Web and dead destinations go unconditionally: neither can be reached by this reader. A
    cross-reference goes only where a Footnote Apparatus is recognised, because without one it
    may be the very footnote reference the rule exists to protect.
    """

    return rules.apparatus if kind == "cross-reference" else True


def _unwrapped(attribute: object, inlines: list[object]) -> object:
    """Drop the destination while keeping the visible text and any target the link itself was.

    A `Link` may carry the identifier another link points at, so an attribute-bearing one becomes
    a `Span` rather than losing its anchor and turning a working cross-reference into a dead one.
    An empty attribute leaves nothing to keep, so its inlines are spliced in unwrapped.
    """

    if _empty_attribute(attribute):
        return _Spliced(inlines)
    return {"t": SPAN, "c": [attribute, inlines]}


def _empty_attribute(attribute: object) -> bool:
    values = sequence(attribute)
    if len(values) != ATTRIBUTE_PARTS:
        return False
    identifier, classes, pairs = values
    return not text(identifier) and not sequence(classes) and not sequence(pairs)


def _at(content: object, index: int) -> object:
    values = sequence(content)
    return values[index] if index < len(values) else None


def _interlock(stripping: Stripping) -> dict[str, object]:
    """Report the counted zeros the interlock turns on, whether or not it engaged."""

    return {
        "apparatus_recognised": stripping.apparatus,
        "engaged": stripping.interlocked,
        "in_book_links": quantity(len(stripping.in_book), "links"),
        "notes": quantity(stripping.notes, "notes"),
    }


def _kind_counts(stripping: Stripping, kind: str) -> dict[str, object]:
    return _counts([link for link in stripping.links if link.kind == kind])


def _counts(links: list[ClassifiedLink]) -> dict[str, object]:
    """Count one selection of links before stripping, after it, and the difference."""

    removed = sum(1 for link in links if link.removed)
    return {
        "after": quantity(len(links) - removed, "links"),
        "before": quantity(len(links), "links"),
        "removed": quantity(removed, "links"),
    }


def _strip_note(stripping: Stripping) -> str:
    if not stripping.activated:
        return STRIP_INACTIVE
    if not stripping.links:
        return STRIP_NOTHING
    if stripping.interlocked:
        return STRIP_INTERLOCKED
    return STRIP_APPLIED
