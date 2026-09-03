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
from tests.prepared_epub import PreparedEpub
from tests.public_cli import prepare

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


def failures(report: Any) -> list[Any]:
    return report["refusal"]["fact"]["failures"]


def test_a_base64_png_is_read_from_the_document_it_arrived_in(tmp_path: Path) -> None:
    png = grayscale_png(tmp_path / "square-0.png", width=4, height=3).read_bytes()
    prepared_source = write_markdown(
        tmp_path / "source-0.md", document(base64_uri(png, "image/png"))
    )
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    output, report = journey.output, journey.report

    assert report["outcome"] == "completed"
    record = report["preparation"]["images"]["records"][0]
    assert record["source"]["measured_media_type"] == "image/png"
    assert (record["source"]["width"]["value"], record["source"]["height"]["value"]) == (4, 3)
    book = PreparedEpub(output)
    packaged = book.media_resources()[record["artifact"]["path"].removeprefix("EPUB/")]
    assert packaged == png


def test_a_percent_encoded_svg_is_read_the_same_way(tmp_path: Path) -> None:
    """RFC 2397's other form. An extractor that does not base64 its icons is not a special case."""

    reference = f"data:image/svg+xml,{quote(SVG)}"
    prepared_source = write_markdown(tmp_path / "source-0.md", document(reference))
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    _, report = journey.output, journey.report

    assert report["outcome"] == "completed"
    record = report["preparation"]["images"]["records"][0]
    assert record["source"]["measured_media_type"] == "image/svg+xml"


def test_the_media_type_the_document_claims_is_not_believed(tmp_path: Path) -> None:
    """The bytes decide, exactly as they do for a file on disk or a fetched resource."""

    png = grayscale_png(tmp_path / "lied-0.png").read_bytes()
    prepared_source = write_markdown(
        tmp_path / "source-0.md", document(base64_uri(png, "image/jpeg"))
    )
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    _, report = journey.output, journey.report

    assert report["outcome"] == "completed"
    record = report["preparation"]["images"]["records"][0]
    assert record["source"]["measured_media_type"] == "image/png"


def test_a_reference_with_no_payload_separator_is_not_a_data_uri(tmp_path: Path) -> None:
    prepared_source = write_markdown(tmp_path / "source-0.md", document("data:image/png;base64"))
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    _, report = journey.output, journey.report

    assert report["outcome"] == "refused"
    assert failures(report)[0]["reason"] == "malformed-inline-reference"


def test_a_payload_that_will_not_decode_says_so_rather_than_blaming_the_location(
    tmp_path: Path,
) -> None:
    prepared_source = write_markdown(
        tmp_path / "source-0.md", document("data:image/png;base64,AAAAA")
    )
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    _, report = journey.output, journey.report

    assert report["outcome"] == "refused"
    assert failures(report)[0]["reason"] == "undecodable-inline-data"


def test_a_payload_that_decodes_to_something_other_than_an_image_measures_as_such(
    tmp_path: Path,
) -> None:
    reference = base64_uri(b"not an image at all", "image/png")
    prepared_source = write_markdown(tmp_path / "source-0.md", document(reference))
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    _, report = journey.output, journey.report

    assert report["outcome"] == "refused"
    assert failures(report)[0]["reason"] == "unmeasurable-bytes"


def test_no_report_line_carries_the_payload(tmp_path: Path) -> None:
    """A base64 SVG runs to thousands of characters. One elided name stands in for it everywhere,
    in the refusal a reader sees and in the record a completed run keeps."""

    png = grayscale_png(tmp_path / "bounded-0.png").read_bytes()
    completed_reference = base64_uri(png, "image/png")
    prepared_source = write_markdown(tmp_path / "source-0.md", document(completed_reference))
    journey = prepare(tmp_path, prepared_source, expected_exit=None)
    _, completed = journey.output, journey.report
    prepared_source = write_markdown(
        tmp_path / "control.md", document(base64_uri(b"nothing", "image/png"))
    )
    journey2 = prepare(tmp_path, prepared_source, expected_exit=None)
    _, refused = journey2.output, journey2.report

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
