from galley.document.baseline import (
    BLOCKS,
    INLINES,
    LABELLED,
    OPAQUE,
    SPACING,
    WRAPPERS,
    preservation_baseline,
)
from galley.release_data import MODELLED_SET, PANDOC_AST, names

ATTR: list[object] = ["", [], []]


def words(*parts: str) -> list[dict[str, object]]:
    inlines: list[dict[str, object]] = []
    for index, part in enumerate(parts):
        if index:
            inlines.append({"t": "Space"})
        inlines.append({"t": "Str", "c": part})
    return inlines


def figure(caption: list[dict[str, object]], alt: list[dict[str, object]]) -> dict[str, object]:
    image = {"t": "Image", "c": [ATTR, alt, ["figure.png", ""]]}
    return {
        "t": "Figure",
        "c": [
            ATTR,
            [None, [{"t": "Plain", "c": caption}]],
            [{"t": "Plain", "c": [image]}],
        ],
    }


def test_a_figure_caption_repeating_its_alt_text_is_counted_once() -> None:
    """Pandoc's implicit figures copy the alt into the caption; two copies would demand two."""

    ast: dict[str, object] = {
        "blocks": [figure(words("A", "river", "diagram"), words("A", "river", "diagram"))]
    }

    assert preservation_baseline(ast) == ("A river diagram\n", 1)


def test_a_figure_caption_that_differs_from_its_alt_keeps_both() -> None:
    ast: dict[str, object] = {
        "blocks": [figure(words("A", "caption", "sentence."), words("Distinctive", "fallback"))]
    }

    assert preservation_baseline(ast) == ("Distinctive fallback\nA caption sentence.\n", 2)


def test_the_reader_takes_its_vocabulary_from_gated_release_data() -> None:
    assert BLOCKS == names(PANDOC_AST, "blocks")
    assert INLINES == names(PANDOC_AST, "inlines")


def test_every_shape_rule_names_a_real_pandoc_constructor() -> None:
    """A typo in a shape rule would silently drop reader-visible text from the baseline."""

    assert SPACING | WRAPPERS | LABELLED <= INLINES
    assert OPAQUE <= BLOCKS | INLINES


def test_the_modelled_set_only_names_blocks_and_inlines() -> None:
    assert names(MODELLED_SET, "constructors") <= BLOCKS | INLINES
