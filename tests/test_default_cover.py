"""A source with no cover-image receives a deterministic title-and-author Default Cover."""

import hashlib
import json
from pathlib import Path
from collections.abc import Callable
from typing import Any, cast

import pytest
from PIL import Image

from tests.article_fixtures import ARTICLE
from tests.article_server import served
from tests.image_fixtures import grayscale_png
from tests.markdown_fixtures import PLAIN_BOOK, write_markdown
from tests.prepared_epub import media_resources
from tests.public_cli import public_cli_commands, run_command
from tests.test_cover_artwork import DIRECTIONS, FONT

TITLE = "A Plain Book"
AUTHOR = "Ada Lovelace"
SOURCE_COVER = """---
title: A Distinct Cover
author: Example Author
cover-image: cover.png
---

# A Distinct Cover

A work that already names its cover.
"""
ILLUSTRATED = """---
title: An Illustrated Essay
author: Ada Lovelace
---

# An Illustrated Essay

A ![body figure](figure.png) in the article body.
"""
RENAMED = """---
title: A Renamed Book
author: Ada Lovelace
---

# A Renamed Book

Prose in the first chapter.
"""


def _prepare(
    tmp_path: Path,
    profile: str,
    index: int,
    command: list[str],
    text: str,
    setup: Callable[[Path], None] | None = None,
) -> tuple[Path, Path, Any]:
    directory = tmp_path / f"{profile}-{index}"
    directory.mkdir()
    if setup is not None:
        setup(directory)
    source = write_markdown(directory / "source.md", text)
    output = directory / "book.epub"
    evidence = directory / "evidence"
    result = run_command(
        command,
        str(source),
        "--output",
        str(output),
        "--evidence-dir",
        str(evidence),
        "--profile",
        profile,
        "--json",
    )
    assert (result.returncode, result.stderr) == (0, "")
    return output, evidence, json.loads(result.stdout)


def _cover(report: Any) -> Any:
    return next(
        entry for entry in report["preparation"]["images"]["records"] if entry["cover"] is True
    )


def test_public_prepare_publishes_a_default_cover_when_the_source_has_no_cover_image(
    tmp_path: Path,
) -> None:
    profile = "x4-crosspoint"
    outputs = [
        _prepare(tmp_path, profile, index, command, PLAIN_BOOK)
        for index, command in enumerate(public_cli_commands("prepare"))
    ]
    payloads: list[bytes] = []

    for output, evidence, report in outputs:
        direction = DIRECTIONS[profile]
        canvas = cast(dict[str, int], direction["canvas"])
        record = _cover(report)
        cover = report["preparation"]["images"]["cover"]
        renderer = record["packaged"]["renderer"]

        assert cover == {"origin": "default-cover", "title": TITLE, "author": AUTHOR}
        assert record["origin"] == "default-cover"
        assert record["reference"] == "cover-image"
        assert record["transform"] == "normalised"
        assert record["packaged"]["measured_media_type"] == "image/png"
        assert record["packaged"]["colour_type"]["value"] == direction["colour_type"]
        assert (record["packaged"]["width"]["value"], record["packaged"]["height"]["value"]) == (
            canvas["width_px"],
            canvas["height_px"],
        )
        assert renderer["tool"] == "resvg"
        assert renderer["matches_pinned_version"] is True
        assert renderer["system_fonts"] is False
        assert renderer["fonts"] == [FONT]
        assert record["artifact"]["cover"] is True
        assert record["artifact"]["referenced"] is True
        member = record["artifact"]["path"].removeprefix("EPUB/")
        payload = media_resources(output)[member]
        assert hashlib.sha256(payload).hexdigest() == record["packaged"]["sha256"]
        payloads.append(payload)

        previews = record["previews"]
        with Image.open(evidence / previews["prepared"]) as prepared:
            assert prepared.size == (canvas["width_px"], canvas["height_px"])
            assert len(set(prepared.convert("L").tobytes())) > 2

    assert payloads[0] == payloads[1]


def test_a_source_cover_image_is_kept(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        held: list[Path] = []
        output, _, report = _prepare(
            tmp_path,
            "x4-crosspoint",
            index,
            command,
            SOURCE_COVER,
            setup=lambda directory: held.append(
                grayscale_png(directory / "cover.png", width=8, height=12)
            ),
        )

        record = _cover(report)
        published = media_resources(output)[record["artifact"]["path"].removeprefix("EPUB/")]
        assert report["preparation"]["images"]["cover"] == {"origin": "source-cover-image"}
        assert record["origin"] == "source-cover-image"
        assert record["src"] == "cover.png"
        assert record["transform"] == "preserved"
        assert published == held[0].read_bytes()


def test_a_body_image_is_not_promoted_to_the_cover(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        held: list[Path] = []
        output, _, report = _prepare(
            tmp_path,
            "x4-crosspoint",
            index,
            command,
            ILLUSTRATED,
            setup=lambda directory: held.append(
                grayscale_png(directory / "figure.png", width=8, height=12)
            ),
        )

        record = _cover(report)
        published = media_resources(output)
        cover_bytes = published[record["artifact"]["path"].removeprefix("EPUB/")]
        body = next(
            entry for entry in report["preparation"]["images"]["records"] if not entry["cover"]
        )
        assert report["preparation"]["images"]["cover"]["origin"] == "default-cover"
        assert body["src"] == "figure.png"
        assert body["artifact"]["cover"] is False
        assert cover_bytes != held[0].read_bytes()
        assert cover_bytes != published[body["artifact"]["path"].removeprefix("EPUB/")]


def test_a_changed_title_changes_the_default_cover(tmp_path: Path) -> None:
    command = public_cli_commands("prepare")[0]
    _, _, original = _prepare(tmp_path, "x4-crosspoint", 0, command, PLAIN_BOOK)
    _, _, renamed = _prepare(tmp_path, "x4-crosspoint", 1, command, RENAMED)

    assert _cover(original)["packaged"]["sha256"] != _cover(renamed)["packaged"]["sha256"]
    assert renamed["preparation"]["images"]["cover"]["title"] == "A Renamed Book"


@pytest.mark.parametrize("profile", tuple(DIRECTIONS))
def test_default_cover_rasterisation_follows_the_profile_cover_direction(
    tmp_path: Path, profile: str
) -> None:
    command = public_cli_commands("prepare")[0]
    _, _, report = _prepare(tmp_path, profile, 0, command, PLAIN_BOOK)

    direction = DIRECTIONS[profile]
    canvas = cast(dict[str, int], direction["canvas"])
    record = _cover(report)
    assert record["origin"] == "default-cover"
    assert record["packaged"]["colour_type"]["value"] == direction["colour_type"]
    assert (record["packaged"]["width"]["value"], record["packaged"]["height"]["value"]) == (
        canvas["width_px"],
        canvas["height_px"],
    )
    assert record["packaged"]["renderer"]["fonts"] == [FONT]


def test_an_article_source_without_a_cover_receives_a_default_cover(tmp_path: Path) -> None:
    with served(ARTICLE) as url:
        for index, command in enumerate(public_cli_commands("prepare", url)):
            output = tmp_path / f"article-{index}.epub"
            result = run_command(
                command,
                "--output",
                str(output),
                "--profile",
                "x4-crosspoint",
                "--json",
            )
            assert (result.returncode, result.stderr) == (0, "")
            report = json.loads(result.stdout)
            record = _cover(report)
            assert report["preparation"]["images"]["cover"] == {
                "origin": "default-cover",
                "title": "A Small Essay",
                "author": "Ada Lovelace",
            }
            assert record["artifact"]["cover"] is True
            member = record["artifact"]["path"].removeprefix("EPUB/")
            assert member in media_resources(output)
