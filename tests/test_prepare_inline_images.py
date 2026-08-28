"""An image whose bytes travelled inside the document, and the bounded name it is reported under.

An extractor turning a page's inline `<svg>` furniture into an `<img>` produces a `data:` `src`.
The reference *is* the resource, so preparation reads it, and every one of these runs through the
installed CLI to prove the whole path rather than the parser alone.
"""

import json
from base64 import b64encode
from pathlib import Path
from typing import Any
from urllib.parse import quote

from galley.images.inline import ELISION, LABEL_LIMIT, inline_label

from tests.image_fixtures import grayscale_png
from tests.markdown_fixtures import write_markdown
from tests.prepared_epub import media_resources
from tests.public_cli import public_cli_commands, run_command

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M3 3h18v18H3z"/></svg>'


def document(*references: str, title: str = "An Inline Book") -> str:
    """One Markdown source whose pictures are carried inside it rather than named elsewhere."""

    pictures = "\n\n".join(
        f"![picture {number}]({reference})" for number, reference in enumerate(references, start=1)
    )
    return (
        f"---\ntitle: {title}\n---\n\n# {title}\n\n"
        "Prose before the pictures, long enough to read as a document rather than a fragment.\n\n"
        f"{pictures}\n\nProse after the pictures, so the baseline holds words on either side.\n"
    )


def base64_uri(data: bytes, media_type: str) -> str:
    return f"data:{media_type};base64,{b64encode(data).decode('ascii')}"


def prepared(tmp_path: Path, index: int, command: list[str], text: str) -> tuple[Path, Any]:
    source = write_markdown(tmp_path / f"source-{index}.md", text)
    output = tmp_path / f"book-{index}.epub"
    result = run_command(command, str(source), "--output", str(output), *ARGUMENTS)
    return output, json.loads(result.stdout)


def failures(report: Any) -> list[Any]:
    return report["refusal"]["fact"]["failures"]


def test_a_base64_png_is_read_from_the_document_it_arrived_in(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        png = grayscale_png(tmp_path / f"square-{index}.png", width=4, height=3).read_bytes()
        output, report = prepared(tmp_path, index, command, document(base64_uri(png, "image/png")))

        assert report["outcome"] == "completed"
        record = report["preparation"]["images"]["records"][0]
        assert record["source"]["measured_media_type"] == "image/png"
        assert (record["source"]["width"]["value"], record["source"]["height"]["value"]) == (4, 3)
        packaged = media_resources(output)[record["artifact"]["path"].removeprefix("EPUB/")]
        assert packaged == png


def test_a_percent_encoded_svg_is_read_the_same_way(tmp_path: Path) -> None:
    """RFC 2397's other form. An extractor that does not base64 its icons is not a special case."""

    for index, command in enumerate(public_cli_commands("prepare")):
        reference = f"data:image/svg+xml,{quote(SVG)}"
        _, report = prepared(tmp_path, index, command, document(reference))

        assert report["outcome"] == "completed"
        record = report["preparation"]["images"]["records"][0]
        assert record["source"]["measured_media_type"] == "image/svg+xml"


def test_the_media_type_the_document_claims_is_not_believed(tmp_path: Path) -> None:
    """The bytes decide, exactly as they do for a file on disk or a fetched resource."""

    for index, command in enumerate(public_cli_commands("prepare")):
        png = grayscale_png(tmp_path / f"lied-{index}.png").read_bytes()
        _, report = prepared(tmp_path, index, command, document(base64_uri(png, "image/jpeg")))

        assert report["outcome"] == "completed"
        record = report["preparation"]["images"]["records"][0]
        assert record["source"]["measured_media_type"] == "image/png"


def test_a_reference_with_no_payload_separator_is_not_a_data_uri(tmp_path: Path) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        _, report = prepared(tmp_path, index, command, document("data:image/png;base64"))

        assert report["outcome"] == "refused"
        assert failures(report)[0]["reason"] == "malformed-inline-reference"


def test_a_payload_that_will_not_decode_says_so_rather_than_blaming_the_location(
    tmp_path: Path,
) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        _, report = prepared(tmp_path, index, command, document("data:image/png;base64,AAAAA"))

        assert report["outcome"] == "refused"
        assert failures(report)[0]["reason"] == "undecodable-inline-data"


def test_a_payload_that_decodes_to_something_other_than_an_image_measures_as_such(
    tmp_path: Path,
) -> None:
    for index, command in enumerate(public_cli_commands("prepare")):
        reference = base64_uri(b"not an image at all", "image/png")
        _, report = prepared(tmp_path, index, command, document(reference))

        assert report["outcome"] == "refused"
        assert failures(report)[0]["reason"] == "unmeasurable-bytes"


def test_no_report_line_carries_the_payload(tmp_path: Path) -> None:
    """A base64 SVG runs to thousands of characters. One elided name stands in for it everywhere,
    in the refusal a reader sees and in the record a completed run keeps."""

    for index, command in enumerate(public_cli_commands("prepare")):
        png = grayscale_png(tmp_path / f"bounded-{index}.png").read_bytes()
        completed_reference = base64_uri(png, "image/png")
        _, completed = prepared(tmp_path, index, command, document(completed_reference))
        _, refused = prepared(
            tmp_path, index + 100, command, document(base64_uri(b"nothing", "image/png"))
        )

        label = "data:image/png;base64" + ELISION
        record = completed["preparation"]["images"]["records"][0]
        assert (record["src"], record["source"]["path"]) == (label, label)
        assert failures(refused)[0]["src"] == label
        assert b64encode(png).decode("ascii") not in json.dumps(completed)


def test_a_locator_is_still_its_own_name() -> None:
    """Only an inline reference is elided. A path or a URL is already something a reader can act
    on, and shortening it would take that away."""

    assert inline_label("figure.png") == "figure.png"
    assert inline_label("https://example.test/a/very/long/path/to/one/image.png").endswith(".png")
    assert len(inline_label(f"data:image/png;base64,{'A' * 4096}")) <= LABEL_LIMIT + len(ELISION)
