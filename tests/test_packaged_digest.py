"""What `packaged_ast_sha256` names, and why two runs over one source agree about it.

Every other digest in a Report was already reproducible — the Canonical Document's, the
artifact's — and this one was not, for any document carrying an image. Image preparation wrote
each `Image` target as an absolute path inside that run's temporary working copy, so the bytes
hashed differed on every run while the book they produced did not. Repeated builds exposed the
digest drift even though the finished artifacts matched.
"""

import json
import zipfile
from pathlib import Path
from typing import Any

from tests.image_fixtures import grayscale_png
from tests.markdown_fixtures import write_markdown
from tests.public_cli import public_cli_commands, run_command

ARGUMENTS = ("--profile", "x4-crosspoint", "--json")
# Its own level-1 heading, so nothing bounds an identifier and the only transform that could
# change the AST is image preparation.
PLAIN = "---\ntitle: A Plain Book\n---\n\n# A Plain Book\n\nWords and more words follow here.\n"
ILLUSTRATED = f"{PLAIN}\n![alt words](figure.png)\n"


def prepared(tmp_path: Path, index: int, command: list[str], source: Path) -> Any:
    output = tmp_path / f"book-{index}.epub"
    result = run_command(command, str(source), "--output", str(output), *ARGUMENTS)
    assert (result.returncode, result.stderr) == (0, "")
    return output, json.loads(result.stdout)


def packaged(report: Any) -> Any:
    return report["preparation"]["canonical_document"]


def fired(report: Any) -> set[str]:
    return {
        entry["name"] for entry in report["preparation"]["transforms"] if entry["fired"] is True
    }


def test_two_runs_over_one_illustrated_source_hash_the_same_bytes(tmp_path: Path) -> None:
    """The defect, at its minimum: same source, same book, different digest on every run."""

    grayscale_png(tmp_path / "figure.png", width=8, height=8)
    source = write_markdown(tmp_path / "illustrated.md", ILLUSTRATED)

    for index, command in enumerate(public_cli_commands("prepare")):
        _, one = prepared(tmp_path, index, command, source)
        _, two = prepared(tmp_path, index + 100, command, source)

        assert packaged(one)["packaged_ast_sha256"] == packaged(two)["packaged_ast_sha256"]
        assert one["artifact"]["sha256"] == two["artifact"]["sha256"]


def test_the_digest_names_the_bytes_the_writer_was_handed(tmp_path: Path) -> None:
    """Not a normalised stand-in for them. The AST carries the packaged file's name, chosen by
    reading order and the same on every run, and packaging tells the writer where to look."""

    grayscale_png(tmp_path / "figure.png", width=8, height=8)
    source = write_markdown(tmp_path / "illustrated.md", ILLUSTRATED)

    for index, command in enumerate(public_cli_commands("prepare")):
        artifact, report = prepared(tmp_path, index, command, source)

        # The image is in the book, which is what makes the bare name a real reference rather
        # than a tidier-looking one the writer could not resolve.
        with zipfile.ZipFile(artifact) as archive:
            assert [name for name in archive.namelist() if name.startswith("EPUB/media/")]
        assert report["preparation"]["images"]["totals"]["references"]["value"] == 1
        assert report["preparation"]["images"]["preservation"]["mapped"]["value"] == 1


def test_a_document_no_transform_changed_reports_it_was_not_transformed(tmp_path: Path) -> None:
    """`transformed` is the digest comparison, so it moved with the temporary directory too."""

    source = write_markdown(tmp_path / "plain.md", PLAIN)

    for index, command in enumerate(public_cli_commands("prepare")):
        _, report = prepared(tmp_path, index, command, source)

        assert packaged(report)["transformed"] is False
        assert packaged(report)["packaged_ast_sha256"] == packaged(report)["retained_ast_sha256"]


def test_an_illustrated_document_is_transformed_and_says_which_transform_did_it(
    tmp_path: Path,
) -> None:
    """The other half, and it is what stops `transformed` reading as an accident: an illustrated
    document *was* changed — its image targets were repointed at what preparation packaged — and
    the transform that did it reports itself in the same Report."""

    grayscale_png(tmp_path / "figure.png", width=8, height=8)
    source = write_markdown(tmp_path / "illustrated.md", ILLUSTRATED)

    for index, command in enumerate(public_cli_commands("prepare")):
        _, report = prepared(tmp_path, index, command, source)

        assert packaged(report)["transformed"] is True
        assert "image-preparation" in fired(report)
