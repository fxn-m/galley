"""Extract reader-visible text from artifact spine documents in reading order."""

from collections.abc import Sequence
from xml.etree.ElementTree import Element

BLOCKS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
)
SKIPPED = frozenset({"head", "script", "style", "template"})


def visible_spine_segments(
    documents: Sequence[tuple[str, Element]],
) -> tuple[str, ...]:
    """Return block-separated visible body text, including image alt fallback."""

    segments: list[str] = []
    for _, root in documents:
        body = next((element for element in root.iter() if _tag(element) == "body"), None)
        if body is not None:
            segments.extend(_segments(body))
    return tuple(segments)


def _segments(element: Element) -> list[str]:
    segments: list[str] = []
    current = [element.text or ""]
    for child in element:
        tag = _tag(child)
        if tag in SKIPPED:
            pass
        elif tag in BLOCKS:
            _append(segments, current)
            current = []
            segments.extend(_segments(child))
        else:
            current.append(_inline_text(child))
        current.append(child.tail or "")
    _append(segments, current)
    return segments


def _inline_text(element: Element) -> str:
    tag = _tag(element)
    if tag in SKIPPED:
        return ""
    if tag == "br":
        return " "
    text = (element.get("alt") or "") if tag == "img" else (element.text or "")
    pieces = [text]
    for child in element:
        pieces.extend((_inline_text(child), child.tail or ""))
    visible = "".join(pieces)
    # A generated note-reference number is rendered as its own superscript token even when its
    # anchor directly follows a word. Keep that semantic boundary in the extracted text so the
    # added number cannot swallow the source token beside it (for example, ``Termword`` + ``5``).
    return f" {visible} " if _is_noteref(element) else visible


def _append(segments: list[str], pieces: list[str]) -> None:
    visible = " ".join("".join(pieces).split())
    if visible:
        segments.append(visible)


def _tag(element: Element) -> str:
    return element.tag.rsplit("}", 1)[-1].lower()


def _is_noteref(element: Element) -> bool:
    return any(
        attribute.rsplit("}", 1)[-1].lower() in {"role", "type"}
        and value in {"doc-noteref", "noteref"}
        for attribute, values in element.attrib.items()
        for value in values.lower().split()
    )
