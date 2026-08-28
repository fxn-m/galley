"""The one metadata field `localise` rewrites, and what a book built from it carries.

Pandoc reads a remote `cover-image` as metadata rather than as an `Image` node. Localisation still
rewrites it: the Repair Set promises a bounded locator repair, and validation does not impose an
arbitrary node-type restriction on that repair.

Every retrieval here is real HTTP over loopback, as in `tests/test_localise.py`.
"""

import json
from pathlib import Path
from typing import cast

from galley.localisation.references import localised_document
from tests.localisation_fixtures import (
    PROFILE,
    Response,
    localised,
    png_bytes,
    read_json,
    serving,
)
from tests.prepared_epub import media_resources
from tests.public_cli import public_cli_commands, run_command


def covered_source(path: Path, cover: str, *pictures: str) -> Path:
    """Write a Markdown source whose cover image lives on the web, as a saved article's does."""

    body = "\n\n".join(f"![picture {n}]({p})" for n, p in enumerate(pictures, start=1))
    _ = path.write_text(
        f"---\ntitle: A Covered Clipping\ncover-image: {cover}\n---\n\n# A Covered Clipping\n\n"
        f"Prose long enough to read as a document rather than as a fragment of one.\n\n{body}\n",
        encoding="utf-8",
    )
    return path


def test_a_remote_cover_image_is_localised_and_the_book_carries_it(tmp_path: Path) -> None:
    """Exercise remote cover localisation end to end rather than asserting its intermediate.

    The cover is retrieved once, the rewritten document names the
    local file, and an ordinary agent-assisted `prepare` over that Repair Set builds a book whose
    cover is those bytes.
    """

    cover = png_bytes(tmp_path, "cover.png")
    with serving({"/cover.png": Response(cover)}) as origin:
        source = covered_source(tmp_path / "clip.md", f"{origin}/cover.png")
        document = localised(source, tmp_path / "repair")

    assert document["outcome"] == "completed", document
    named = {entry["identifier"]: entry for entry in document["references"]}
    assert "cover-image" in named
    assert named["cover-image"]["locator"] == f"{origin}/cover.png"

    evidence = tmp_path / "repair"
    built = run_command(
        public_cli_commands("prepare", str(source))[0],
        *PROFILE,
        "--output",
        str(tmp_path / "after.epub"),
        "--json",
        "--inspection-report",
        str(evidence / "report.json"),
        "--canonical-document",
        str(evidence / "canonical-document.json"),
        "--preservation-baseline",
        str(evidence / "preservation-baseline.txt"),
    )

    assert built.returncode == 0, built.stdout
    assert json.loads(built.stdout)["outcome"] == "completed"
    assert len(media_resources(tmp_path / "after.epub")) == 1


def test_the_cover_a_markdown_source_states_is_rewritten_in_place(tmp_path: Path) -> None:
    """YAML frontmatter always reaches the AST as `MetaInlines` — measured, both bare and quoted —
    so this is the carrier every Markdown source actually produces. The shape is kept and only the
    locator moves."""

    with serving({"/cover.png": Response(png_bytes(tmp_path, "cover.png"))}) as origin:
        source = covered_source(tmp_path / "clip.md", f"{origin}/cover.png")
        document = localised(source, tmp_path / "repair")

    assert document["outcome"] == "completed", document
    stated = read_json(tmp_path / "repair" / "canonical-document.json")["pandoc"]["meta"][
        "cover-image"
    ]
    assert stated["t"] == "MetaInlines"
    assert origin not in json.dumps(stated)
    assert str(tmp_path / "repair") in json.dumps(stated)


def test_a_cover_carried_as_a_string_is_rewritten_as_a_string(tmp_path: Path) -> None:
    """`MetaString` cannot come from frontmatter — only from `--metadata` — but a repaired
    Canonical Document an agent hands in can carry one, and `_cover_locator` has always read
    both. So the rewrite is held to both, here at the seam that can produce one."""

    document: dict[str, object] = {
        "schema": "galley/canonical-document/1",
        "title": "A Covered Clipping",
        "author": None,
        "source_url": None,
        "warnings": cast(list[object], []),
        "pandoc": {
            "pandoc-api-version": [1, 23, 1, 2],
            "meta": {"cover-image": {"t": "MetaString", "c": "https://example.com/cover.png"}},
            "blocks": [],
        },
    }

    rewritten = localised_document(document, {"https://example.com/cover.png": "/local/cover.png"})

    pandoc = cast(dict[str, object], rewritten["pandoc"])
    stated = cast(dict[str, object], pandoc["meta"])["cover-image"]
    assert stated == {"t": "MetaString", "c": "/local/cover.png"}


def test_a_cover_that_is_also_shown_in_the_body_is_retrieved_once(tmp_path: Path) -> None:
    """One locator, one retrieval, one entry in the record. Naming it twice would fetch the same
    bytes twice and make the document say the source pulled more than it did."""

    with serving({"/shared.png": Response(png_bytes(tmp_path, "shared.png"))}) as origin:
        source = covered_source(
            tmp_path / "clip.md", f"{origin}/shared.png", f"{origin}/shared.png"
        )
        document = localised(source, tmp_path / "repair")

    assert document["outcome"] == "completed", document
    assert [entry["locator"] for entry in document["references"]] == [f"{origin}/shared.png"]
    rewritten = read_json(tmp_path / "repair" / "canonical-document.json")
    # Both the cover and the body picture point at the one file that was written.
    assert origin not in json.dumps(rewritten["pandoc"])


def test_a_cover_that_cannot_be_retrieved_refuses_the_whole_run(tmp_path: Path) -> None:
    """Exactly as an image `src` does: no partial Repair Set, and the boundary names retrieval
    rather than the withdrawn `cover-image` reason."""

    with serving({"/a.png": Response(png_bytes(tmp_path))}) as origin:
        source = covered_source(tmp_path / "clip.md", f"{origin}/missing.png", f"{origin}/a.png")
        document = localised(source, tmp_path / "repair")

    assert document["outcome"] == "refused"
    assert document["refusal"]["boundary"] == "unretrievable-image"
    assert not (tmp_path / "repair" / "canonical-document.json").exists()
