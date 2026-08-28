"""Drop the raw HTML that would leave a chapter unparseable, and keep the raw HTML that would not.

Pandoc's readers produce `RawBlock`/`RawInline` html from markup they decline to structure, and
its writers emit that payload verbatim. XHTML has to be well-formed XML, so a single tag with no
partner takes the whole book down. One observed code sample carried an unmatched `</div>` inside
a tab-indented list item; EPUBCheck reported a fatal `RSC-016` and the
text measurement read 2,299 of 27,298 tokens — a document reported as losing four thousand words
that had lost none.

Balance is judged across the document rather than inside one node, because the shape that actually
occurs is a matched pair split across two: a `<sub>` in one `RawInline` and its `</sub>` in another
are one element, and dropping either would create the very problem this exists to stop.

A structural tag carries no reader-visible text — `document/baseline.py` already treats raw markup
as opaque for exactly that reason — so dropping one loses nothing a reader was going to see. Text
Preservation proves that claim on every run.
"""

from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import cast

from galley.json_reading import mapping, sequence, text
from galley.report.quantities import quantity

RAW = ("RawBlock", "RawInline")
# The raw formats an EPUB3 writer emits into the book. Raw markup in any other format is dropped
# by the writer itself, so it can never make a chapter unparseable and is not this pass's business.
EMITTED = frozenset({"html", "xhtml", "html4", "html5"})
# Elements HTML closes for you. One of these is complete on its own and never waits for a partner.
VOID = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }
)  # fmt: skip
RAW_HTML_BALANCE = "raw-html-balance"
BALANCE_NOTE = (
    "Raw HTML is emitted into the book verbatim, and a tag with no partner leaves the chapter "
    "unparseable — which reports as lost text rather than as a broken book. Every unbalanced raw "
    "node is dropped and named here. A structural tag carries no reader-visible word, so Text "
    "Preservation proves nothing went with it."
)


@dataclass(frozen=True)
class Balance:
    """One balancing pass: the document it produced, and every payload it had to drop."""

    ast: dict[str, object]
    dropped: list[str] = field(default_factory=list[str])

    @property
    def fired(self) -> bool:
        return bool(self.dropped)


def balance_raw_html(ast: dict[str, object]) -> Balance:
    """Rebuild the document without the raw HTML nodes whose tags have no partner.

    Repeated until nothing more is unbalanced: dropping a node takes its balanced tags with it, so
    a partner elsewhere can be orphaned by the very pass that tidied up. The set only ever grows,
    so this settles.
    """

    nodes = _raw_nodes(ast)
    dropped: set[int] = set()
    while (found := _unbalanced(nodes, dropped)) - dropped:
        dropped |= found
    if not dropped:
        return Balance(ast=ast)
    return Balance(
        ast=cast(dict[str, object], _rebuilt(ast, dropped)),
        dropped=[_payload(node) or "" for node in nodes if id(node) in dropped],
    )


def _raw_nodes(value: object) -> list[dict[str, object]]:
    """Every node carrying an emitted raw HTML payload, in reading order."""

    if isinstance(value, list):
        return [found for item in cast(list[object], value) for found in _raw_nodes(item)]
    if not isinstance(value, dict):
        return []
    node = cast(dict[str, object], value)
    if _payload(node) is not None:
        return [node]
    return [found for item in node.values() for found in _raw_nodes(item)]


def _payload(node: dict[str, object]) -> str | None:
    """Read one node's emitted raw HTML payload, or nothing where it carries none."""

    if text(node.get("t")) not in RAW:
        return None
    content = sequence(node.get("c"))
    if len(content) < 2 or (text(content[0]) or "").lower() not in EMITTED:
        return None
    return text(content[1]) or ""


class _Tags(HTMLParser):
    """Read the surviving payloads as one tag stream and say which nodes hold an orphan.

    The standard library's own HTML parser rather than a pattern of this project's devising: it
    knows which construct is a tag, which is a comment and which is a declaration, and this
    repository allows no production regex precisely so that a decision like that is never
    re-derived by hand. It is deliberately lenient about structure, which is what makes it useful
    here — it reports a closing tag whether or not anything opened.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.node = 0
        self.stack: list[tuple[str, int]] = []
        self.unbalanced: set[int] = set()

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag.lower() not in VOID:
            self.stack.append((tag.lower(), self.node))

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in VOID:
            return
        if not any(opened == lowered for opened, _ in self.stack):
            self.unbalanced.add(self.node)
            return
        while self.stack[-1][0] != lowered:
            self.unbalanced.add(self.stack.pop()[1])
        _ = self.stack.pop()


def _unbalanced(nodes: list[dict[str, object]], dropped: set[int]) -> set[int]:
    """Name every node holding a tag with no partner, reading the survivors as one stream."""

    tags = _Tags()
    for node in nodes:
        if id(node) in dropped:
            continue
        tags.node = id(node)
        tags.feed(_payload(node) or "")
    tags.close()
    return dropped | tags.unbalanced | {identity for _, identity in tags.stack}


def _rebuilt(value: object, dropped: set[int]) -> object:
    """Rebuild the tree, leaving out each raw node the balance pass named."""

    if isinstance(value, list):
        return [
            _rebuilt(item, dropped) for item in cast(list[object], value) if id(item) not in dropped
        ]
    if not isinstance(value, dict):
        return value
    node = cast(dict[str, object], value)
    return {key: _rebuilt(item, dropped) for key, item in node.items()}


def raw_html_transform(balance: Balance) -> dict[str, object]:
    """State how much raw HTML was dropped and exactly which payloads went.

    Named rather than counted: "one node was dropped" cannot tell a reader whether the thing that
    left their book was a stray `</div>` or something they wrote.
    """

    return {
        "name": RAW_HTML_BALANCE,
        "fired": balance.fired,
        "dropped": quantity(len(balance.dropped), "nodes"),
        "payloads": list(balance.dropped),
        "note": BALANCE_NOTE,
    }


def malformed_documents(facts: dict[str, object]) -> list[str]:
    """Name every content document the built artifact carries that is not well-formed XML."""

    return sorted(
        location
        for problem in sequence(facts.get("problems"))
        if (entry := mapping(problem)).get("kind") == "malformed-xml"
        and (location := text(entry.get("location"))) is not None
    )
