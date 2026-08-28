"""Recognise the Footnote Apparatus by its shape, not by markup that carries its name.

Every case here once recovered and should not have. They are kept apart from the recovery
behaviour tests because they ask a different question: not "what does recovery do with an
apparatus", but "what counts as one".
"""

import json
from pathlib import Path

from tests.article_fixtures import filler
from tests.article_server import defuddle_returning, served
from tests.public_cli import run_public_cli


def test_only_a_closed_container_holding_its_own_endnotes_is_an_apparatus(tmp_path: Path) -> None:
    """Recognition is of a shape, so markup that merely carries the name is not that shape.

    Each of these once recovered. The first put the endnotes outside the section it emitted,
    which is the "every one of them is empty" result the second half of the relabel exists to
    prevent; the second spliced a closing tag at offset zero; the third swallowed an ordinary
    trailing list as endnotes.
    """

    lookalikes = {
        "a heading that merely carries the identifier": (
            '<h2 id="footnotes">Notes</h2><ol><li id="fn:1"><p>Body here.</p></li></ol>'
        ),
        "a void element that never closes": (
            '<hr id="footnotes"><ol><li id="fn:1"><p>Body here.</p></li></ol>'
        ),
    }
    for label, tail in lookalikes.items():
        content = (
            '<article><p>Alpha bravo charlie.<sup id="fnref:1"><a href="#fn:1">1</a></sup></p>'
            f"{filler()}{tail}</article>"
        )
        command = defuddle_returning(tmp_path / f"defuddle-{abs(hash(label))}", content)

        with served() as url:
            results = run_public_cli(
                "inspect",
                url,
                "--profile",
                "x4-crosspoint",
                "--json",
                environment={"GALLEY_DEFUDDLE": str(command)},
            )

        assert [result.returncode for result in results] == [0, 0], label
        for result in results:
            report = json.loads(result.stdout)
            recovery = report["extraction"]["footnote_recovery"]
            assert recovery["outcome"] == "skipped", label
            assert recovery["recovered_notes"]["value"] == 0, label
            # Nothing was relabelled, so no empty note and no corrupted document reached Pandoc.
            assert report["canonical_document"]["reading"]["notes"]["value"] == 0, label


def test_an_ordinary_list_after_the_endnotes_is_not_part_of_them(tmp_path: Path) -> None:
    """The container's extent decides what an endnote is, not the order things appear in."""

    content = (
        '<article><p>Alpha bravo charlie.<sup id="fnref:1"><a href="#fn:1">1</a></sup></p>'
        f"{filler()}"
        '<div id="footnotes"><ol><li id="fn:1"><p>Firstnote body here.</p></li></ol></div>'
        "<ul><li>Related reading</li><li>More links</li></ul></article>"
    )
    command = defuddle_returning(tmp_path / "defuddle", content)

    with served() as url:
        results = run_public_cli(
            "inspect",
            url,
            "--profile",
            "x4-crosspoint",
            "--json",
            environment={"GALLEY_DEFUDDLE": str(command)},
        )

    assert [result.returncode for result in results] == [0, 0]
    for result in results:
        recovery = json.loads(result.stdout)["extraction"]["footnote_recovery"]
        assert recovery["outcome"] == "recovered"
        assert recovery["definitions"]["value"] == 1
        assert recovery["recovered_notes"]["value"] == 1


def test_a_note_carrying_its_own_list_is_read_whole(tmp_path: Path) -> None:
    """A note ends at its own end tag, so emptiness is judged on the note and not a fragment."""

    content = (
        '<article><p>Alpha bravo charlie.<sup id="fnref:1"><a href="#fn:1">1</a></sup></p>'
        f"{filler()}"
        '<div id="footnotes"><ol><li id="fn:1"><ul><li>An inner item.</li></ul>'
        "<p>Realtext body here.</p></li></ol></div></article>"
    )
    command = defuddle_returning(tmp_path / "defuddle", content)

    with served() as url:
        results = run_public_cli(
            "inspect",
            url,
            "--profile",
            "x4-crosspoint",
            "--json",
            environment={"GALLEY_DEFUDDLE": str(command)},
        )

    assert [result.returncode for result in results] == [0, 0]
    for result in results:
        recovery = json.loads(result.stdout)["extraction"]["footnote_recovery"]
        assert recovery["outcome"] == "recovered"
        assert recovery["definitions"]["value"] == 1
        assert recovery["empty_notes"]["value"] == 0


def test_equal_counts_with_different_identifiers_do_not_report_no_mismatch(
    tmp_path: Path,
) -> None:
    """The mismatch fact counts unpaired identifiers, so it cannot contradict the reason."""

    content = (
        '<article><p>Alpha bravo charlie.<sup id="fnref:1"><a href="#fn:1">1</a></sup></p>'
        f"{filler()}"
        '<div id="footnotes"><ol><li id="fn:9"><p>Firstnote body here.</p></li></ol></div></article>'
    )
    command = defuddle_returning(tmp_path / "defuddle", content)

    with served() as url:
        results = run_public_cli(
            "inspect",
            url,
            "--profile",
            "x4-crosspoint",
            "--json",
            environment={"GALLEY_DEFUDDLE": str(command)},
        )

    assert [result.returncode for result in results] == [0, 0]
    for result in results:
        recovery = json.loads(result.stdout)["extraction"]["footnote_recovery"]
        assert recovery["reason"] == "reference-definition-mismatch"
        assert (recovery["references"]["value"], recovery["definitions"]["value"]) == (1, 1)
        # One reference and one endnote, neither of which names the other.
        assert recovery["mismatch"]["value"] == 2
