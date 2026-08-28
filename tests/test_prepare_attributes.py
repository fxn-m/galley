"""What a prepared book may say in an attribute, and what happens to what it may not.

An EPUB3 content document is XHTML, so an attribute the profile does not admit on the element it
lands on makes the whole book invalid — `<table width="100%">` is the observed case. Pandoc's
readers keep a source element's unmodelled attributes and its writers emit them, and the writer
already rescues most unrecognised names under the format's own `data-` prefix. These hold that
rescue to every name rather than to the ones Pandoc's own list happens to miss.
"""

import json
import zipfile
from pathlib import Path
from typing import Any

from tests.article_fixtures import filler
from tests.article_server import served
from tests.image_fixtures import grayscale_png
from tests.markdown_fixtures import write_markdown
from tests.public_cli import public_cli_commands, run_command

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")
# A real page's presentational table. Pandoc namespaces `align`, `cellpadding` and `bgcolor` under
# `data-` of its own accord and emits `width` verbatim, because `width` is on its list of HTML
# attribute names and that list takes no account of the element.
TABLED = f"""<!doctype html>
<html><head><title>A Tabled Page</title></head><body>
<article>
<h2>A Tabled Page</h2>
<table width="100%" align="left" bgcolor="silver"><tr><td>one</td><td>two</td></tr></table>
{filler()}
</article>
</body></html>
"""


def prepared(tmp_path: Path, index: int, command: list[str], *extra: str) -> tuple[Path, Any]:
    output = tmp_path / f"book-{index}.epub"
    result = run_command(command, "--output", str(output), *ARGUMENTS, *extra)
    assert (result.returncode, result.stderr) == (0, "")
    return output, json.loads(result.stdout)


def namespacing(report: Any) -> Any:
    return next(
        entry
        for entry in report["preparation"]["transforms"]
        if entry["name"] == "attribute-namespacing"
    )


def chapters(artifact: Path) -> str:
    with zipfile.ZipFile(artifact) as archive:
        return "".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.startswith("EPUB/text/")
        )


def test_an_attribute_the_element_does_not_admit_is_namespaced(tmp_path: Path) -> None:
    """`width` is legal on an image and illegal on a table, so the name alone cannot decide it."""

    with served(TABLED) as url:
        for index, command in enumerate(public_cli_commands("prepare", url)):
            artifact, report = prepared(tmp_path, index, command)

            assert report["outcome"] == "completed"
            assert '<table data-width="100%"' in chapters(artifact)
            assert "<table width=" not in chapters(artifact)
            assert {
                "constructor": "Table",
                "element": "table",
                "attribute": "width",
            } in namespacing(report)["renamed"]


def test_the_same_attribute_survives_on_the_element_that_admits_it(tmp_path: Path) -> None:
    source = write_markdown(
        tmp_path / "sized.md",
        "---\ntitle: A Sized Image\n---\n\n# A Sized Image\n\n"
        "Text.\n\n![alt words](figure.png){width=64 height=48}\n\nMore text.\n",
    )
    grayscale_png(tmp_path / "figure.png", width=64, height=48)

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        _, report = prepared(tmp_path, index, command)

        assert report["outcome"] == "completed"
        renamed = {entry["attribute"] for entry in namespacing(report)["renamed"]}
        assert "width" not in renamed and "height" not in renamed


def test_a_globally_admitted_attribute_is_left_alone(tmp_path: Path) -> None:
    """`title`, `role` and `epub:type` are admitted on every element, and `epub:type` is how a
    footnote reference is marked — namespacing one would break the apparatus, not tidy it."""

    source = write_markdown(
        tmp_path / "attributed.md",
        "---\ntitle: An Attributed Book\n---\n\n"
        '# A heading {title="a tooltip" role="heading" custom="x"}\n\nText and more text.\n',
    )

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        artifact, report = prepared(tmp_path, index, command)

        assert report["outcome"] == "completed"
        assert [entry["attribute"] for entry in namespacing(report)["renamed"]] == ["custom"]
        assert 'title="a tooltip"' in chapters(artifact)
        assert 'role="heading"' in chapters(artifact)


def test_namespacing_an_attribute_moves_no_word(tmp_path: Path) -> None:
    """An attribute is not a word. Text Preservation is what proves the rename left the prose
    exactly where it was."""

    with served(TABLED) as url:
        for index, command in enumerate(public_cli_commands("prepare", url)):
            _, report = prepared(tmp_path, index, command)

            assert report["outcome"] == "completed"
            assert report["artifact"]["text_preservation"]["claimed"] is True
            assert report["artifact"]["text_preservation"]["tokens"]["unexpected_missing"] == []


def test_a_document_with_nothing_to_namespace_says_so(tmp_path: Path) -> None:
    """ "Nothing was namespaced" and "the step is broken" have to stay distinguishable."""

    source = write_markdown(
        tmp_path / "plain.md",
        "---\ntitle: A Plain Book\n---\n\n# A Plain Book\n\nText and more text.\n",
    )

    for index, command in enumerate(public_cli_commands("prepare", str(source))):
        _, report = prepared(tmp_path, index, command)

        assert report["outcome"] == "completed"
        assert namespacing(report) == {
            **namespacing(report),
            "fired": False,
            "renamed": [],
            "count": {"basis": "measured", "unit": "attributes", "value": 0},
        }
