"""Every way a localisation refuses, and the one thing all of them have in common.

Nothing is written. A Repair Set missing one picture would be refused by the very `prepare` it
exists to feed, and a partial one on disk looks finished — so the run stops whole, names the
reference that stopped it, and leaves the directory as it found it.

The bounds themselves are exercised through the installed CLI wherever the command line can reach
them, because the hardened address rule is the only one a user can produce.
"""

import json
from pathlib import Path

from base64 import b64encode

from galley.tools.fetching import MAXIMUM_BYTES
from tests.image_fixtures import grayscale_png
from tests.localisation_fixtures import (
    PROFILE,
    Response,
    illustrated_source,
    localised,
    png_bytes,
    serving,
)
from tests.public_cli import public_cli_commands, run_command


def test_a_source_with_no_remote_image_refuses_rather_than_doing_empty_work(tmp_path: Path) -> None:
    """Localisation is for a document whose pictures are elsewhere. A source that has none is
    told so, rather than being handed a Repair Set identical to its own inspection."""

    source = illustrated_source(tmp_path / "local.md", "figure.png")
    _ = grayscale_png(tmp_path / "figure.png")

    result = run_command(
        public_cli_commands("localise", str(source))[0],
        *PROFILE,
        "--evidence-dir",
        str(tmp_path / "repair"),
        "--json",
    )

    assert result.returncode == 3
    document = json.loads(result.stdout)
    assert document["refusal"]["boundary"] == "no-remote-images"
    assert not (tmp_path / "repair").exists()


def test_an_article_url_refuses_because_its_images_already_localise(tmp_path: Path) -> None:
    """Preparation retrieves an Article-Like Page's images, so localising one would retrieve the
    same bytes a second time under a different name."""

    result = run_command(
        public_cli_commands("localise", "https://example.com/article")[0],
        *PROFILE,
        "--evidence-dir",
        str(tmp_path / "repair"),
        "--json",
    )

    assert result.returncode == 3
    document = json.loads(result.stdout)
    assert document["refusal"]["boundary"] == "unsupported-source-kind"
    assert document["refusal"]["fact"]["kind"] == "article-url"
    assert not (tmp_path / "repair").exists()


def test_a_locally_resolving_host_is_refused_through_the_installed_cli(tmp_path: Path) -> None:
    """The anti-SSRF bound, on the only surface a user has. The command line cannot widen the
    permitted address range, so a document naming a loopback host is refused before a socket is
    opened for it — resolved addresses recorded, and nothing written."""

    with serving({"/a.png": Response(png_bytes(tmp_path))}) as origin:
        source = illustrated_source(tmp_path / "clip.md", f"{origin}/a.png")
        result = run_command(
            public_cli_commands("localise", str(source))[0],
            *PROFILE,
            "--evidence-dir",
            str(tmp_path / "repair"),
            "--json",
        )

    assert result.returncode == 3
    document = json.loads(result.stdout)
    assert document["refusal"]["boundary"] == "blocked-image-host"
    assert document["refusal"]["fact"]["reason"] == "blocked-host"
    assert document["references"][0]["addresses"] == ["127.0.0.1"]
    assert document["references"][0]["path"] is None
    assert not (tmp_path / "repair").exists()


def test_every_way_a_reference_fails_refuses_the_whole_run(tmp_path: Path) -> None:
    """One reference Galley cannot turn into local bytes stops the localisation, whatever went
    wrong — because a Repair Set missing one picture would be refused by the very `prepare` this
    exists to feed, and a partial one on disk looks finished."""

    good = png_bytes(tmp_path)
    cases = {
        "/missing.png": ("http-error", Response(b"gone", 404, "text/plain")),
        "/moved.png": ("redirected", Response(b"", 302, "text/plain", location="/a.png")),
        "/huge.png": ("oversize", Response(b"\0" * (MAXIMUM_BYTES + 1))),
        "/prose.png": ("undecodable", Response(b"this is not an image", 200, "text/plain")),
    }
    with serving({"/a.png": Response(good), **{p: r for p, (_, r) in cases.items()}}) as origin:
        for number, (path, (reason, _)) in enumerate(cases.items()):
            evidence = tmp_path / f"repair-{number}"
            source = illustrated_source(
                tmp_path / f"clip-{number}.md", f"{origin}/a.png", f"{origin}{path}"
            )
            document = localised(source, evidence)

            assert document["outcome"] == "refused", reason
            assert document["refusal"]["boundary"] == "unretrievable-image", reason
            assert document["refusal"]["fact"]["reason"] == reason
            assert document["refusal"]["fact"]["locator"] == f"{origin}{path}"
            assert not evidence.exists(), reason


def test_a_reference_that_is_neither_local_nor_retrievable_refuses(tmp_path: Path) -> None:
    """A `data:` or `ftp:` reference is not a file `prepare` would resolve and not something
    `localise` retrieves, so it is named here rather than left for a later refusal to find."""

    source = illustrated_source(tmp_path / "clip.md", "ftp://example.com/a.png")

    result = run_command(
        public_cli_commands("localise", str(source))[0],
        *PROFILE,
        "--evidence-dir",
        str(tmp_path / "repair"),
        "--json",
    )

    assert result.returncode == 3
    document = json.loads(result.stdout)
    assert document["refusal"]["boundary"] == "unlocalisable-reference"
    assert document["refusal"]["fact"]["reason"] == "unsupported-locator"


def test_the_concise_rendering_names_the_boundary_and_the_reference(tmp_path: Path) -> None:
    """Without `--json` the same facts reach the terminal as prose, from the document alone —
    never a second account of what happened. This is the output a user actually sees."""

    source = illustrated_source(tmp_path / "clip.md", "ftp://example.com/a.png")

    result = run_command(
        public_cli_commands("localise", str(source))[0],
        *PROFILE,
        "--evidence-dir",
        str(tmp_path / "repair"),
    )

    assert result.returncode == 3
    assert result.stdout.splitlines()[:2] == [
        "localise: refused",
        "Profile: x4-crosspoint",
    ]
    assert "Boundary: unlocalisable-reference" in result.stdout
    assert "ftp://example.com/a.png" in result.stdout


def test_an_inline_reference_is_passed_over_rather_than_called_unlocalisable(
    tmp_path: Path,
) -> None:
    """A `data:` reference carries its own bytes, so `prepare` reads it with no network at all.
    Refusing it here would leave a document `prepare` can build and `localise` cannot read."""

    png = grayscale_png(tmp_path / "inline.png").read_bytes()
    inline = "data:image/png;base64," + b64encode(png).decode("ascii")
    source = illustrated_source(tmp_path / "inline.md", inline)

    result = run_command(
        public_cli_commands("localise", str(source))[0],
        *PROFILE,
        "--evidence-dir",
        str(tmp_path / "repair"),
        "--json",
    )

    assert result.returncode == 3
    document = json.loads(result.stdout)
    assert document["refusal"]["boundary"] == "no-remote-images"
