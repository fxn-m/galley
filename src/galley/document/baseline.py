"""Derive the reader-visible text retained as a Preservation Baseline.

The baseline is one block-separated plain-text rendering of a Pandoc AST. Text is emitted only
from constructors Galley recognises as carrying reader-visible characters, so attribute values,
class names and link targets can never be mistaken for prose. Unknown constructors are walked
rather than skipped, because an unmodelled wrapper still holds real text.
"""

from collections.abc import Sequence

from galley.json_reading import mapping, sequence, text
from galley.release_data import PANDOC_AST, names

# Which names are blocks and which are inlines is Pandoc's vocabulary, not Galley's opinion, so
# both come from gated release data. How each one carries its text is this module's own logic.
BLOCKS = names(PANDOC_AST, "blocks")
INLINES = names(PANDOC_AST, "inlines")
SPACING = frozenset({"LineBreak", "SoftBreak", "Space"})
# Constructors whose whole `c` payload is their reader-visible inline content.
WRAPPERS = frozenset(
    {"Emph", "SmallCaps", "Strikeout", "Strong", "Subscript", "Superscript", "Underline"}
)
# Constructors whose reader-visible inline content is the second element of `c`.
LABELLED = frozenset({"Cite", "Image", "Link", "Quoted", "Span"})
# Raw markup is never reader-visible text; carrying it would invent losses that never happened.
OPAQUE = frozenset({"RawBlock", "RawInline"})


def preservation_baseline(ast: dict[str, object]) -> tuple[str, int]:
    """Render one Pandoc AST as Preservation Baseline text and say how many segments it holds."""

    segments = block_segments(sequence(ast.get("blocks")))
    return "".join(f"{segment}\n" for segment in segments), len(segments)


def glyph_occurrences(ast: dict[str, object], codepoints: Sequence[str]) -> dict[str, int]:
    """Count how often each named codepoint appears in reader-visible text, in stable order."""

    visible = "".join(block_segments(sequence(ast.get("blocks"))))
    counted = {name: visible.count(character) for name in codepoints if (character := _glyph(name))}
    return {name: count for name, count in sorted(counted.items()) if count}


def _glyph(name: str) -> str:
    """Read one `U+XXXX` codepoint name, ignoring anything that does not name a character."""

    digits = name[2:] if name.upper().startswith("U+") else ""
    try:
        return chr(int(digits, 16))
    except ValueError:
        return ""


def block_segments(blocks: Sequence[object]) -> list[str]:
    """Render each block as its own baseline segment, in document order."""

    return [segment for block in blocks for segment in _block(mapping(block))]


def inline_text(inlines: Sequence[object]) -> str:
    """Concatenate the reader-visible characters one inline sequence carries."""

    return "".join(_inline(mapping(inline)) for inline in inlines)


def _block(node: dict[str, object]) -> list[str]:
    kind = text(node.get("t")) or ""
    content = node.get("c")
    if kind in {"Para", "Plain"}:
        return _segment(inline_text(sequence(content)))
    if kind == "Header":
        return _segment(inline_text(sequence(_item(content, 2))))
    if kind == "CodeBlock":
        return _segment(text(_item(content, 1)) or "")
    if kind == "LineBlock":
        lines = (inline_text(sequence(line)) for line in sequence(content))
        return _segment("\n".join(lines))
    if kind == "BlockQuote":
        return block_segments(sequence(content))
    if kind == "Div":
        return block_segments(sequence(_item(content, 1)))
    if kind == "BulletList":
        return _walk(content)
    if kind == "OrderedList":
        return _walk(_item(content, 1))
    if kind == "DefinitionList":
        return _definitions(content)
    if kind == "Figure":
        return _figure(content)
    if kind in OPAQUE or kind == "HorizontalRule":
        return []
    return _walk(content)


def _figure(content: object) -> list[str]:
    """Keep a figure's caption only where it says something its images do not.

    Pandoc's implicit figures reuse the image's alt text as the caption, so keeping both would
    put the same words in the baseline twice and demand two occurrences in the built artifact.
    A caption that differs from every alt segment is real text and is kept.

    That demand is what `transforms/figures.py` costs nothing against. A built book renders the
    alt attribute as the device's own image fallback, so it carries the words the baseline asks
    for whether or not Pandoc's derived caption is printed beside it.
    """

    body = block_segments(sequence(_item(content, 2)))
    caption = block_segments(sequence(_item(_item(content, 1), 1)))
    return body + [segment for segment in caption if segment not in body]


def _definitions(content: object) -> list[str]:
    segments: list[str] = []
    for entry in sequence(content):
        segments.extend(_segment(inline_text(sequence(_item(entry, 0)))))
        for definition in sequence(_item(entry, 1)):
            segments.extend(block_segments(sequence(definition)))
    return segments


def _inline(node: dict[str, object]) -> str:
    kind = text(node.get("t")) or ""
    content = node.get("c")
    if kind == "Str":
        return text(content) or ""
    if kind in SPACING:
        return " "
    if kind in {"Code", "Math"}:
        return text(_item(content, 1)) or ""
    if kind in WRAPPERS:
        return inline_text(sequence(content))
    if kind in LABELLED:
        return inline_text(sequence(_item(content, 1)))
    if kind == "Note":
        # Padded on both sides: a note sits inside its paragraph's text, and concatenating it
        # without a separator would glue two real words into one token that survives nowhere.
        return f" {' '.join(block_segments(sequence(content)))} "
    if kind in OPAQUE:
        return ""
    return " ".join(_walk(content))


def _walk(value: object) -> list[str]:
    """Reach the text inside a nested or unmodelled structure without reading its attributes."""

    items = sequence(value)
    if items:
        return [segment for item in items for segment in _walk(item)]
    node = mapping(value)
    kind = text(node.get("t"))
    if kind is None:
        return []
    if kind in BLOCKS:
        return _block(node)
    if kind in INLINES:
        return _segment(_inline(node))
    return _walk(node.get("c"))


def _segment(value: str) -> list[str]:
    stripped = value.strip()
    return [stripped] if stripped else []


def _item(content: object, index: int) -> object:
    values = sequence(content)
    return values[index] if index < len(values) else None
