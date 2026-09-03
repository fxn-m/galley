"""Localise a Markdown source's remote images, and hand the result to an ordinary prepare.

Every retrieval here is real HTTP over loopback (`tests/localisation_fixtures.py` says why that
is both possible and bounded), so what these assert is the transport as well as the decision:
what arrived, what was written, and what was refused whole.
"""

import json
from base64 import b64encode
from hashlib import sha256
from pathlib import Path

from galley.documents import LOCALISATION_SCHEMA
from galley.localisation.render import render_localisation
from tests.image_fixtures import baseline_jpeg
from tests.localisation_fixtures import (
    PROFILE,
    Response,
    blind_to_image_targets,
    file_hashes,
    illustrated_source,
    image_locators,
    localised,
    png_bytes,
    read_json,
    serving,
)
from tests.prepared_epub import media_resources
from tests.public_cli import run_cli
from tests.workspace_fixtures import workspace_environment


def test_localise_writes_a_repair_set_an_ordinary_prepare_accepts(tmp_path: Path) -> None:
    """The whole point, end to end: a Markdown source whose pictures are remote refuses today,
    and after one localisation the same source builds an illustrated book through the ordinary
    agent-assisted repair path — no second image pipeline, no fetch inside `prepare`."""

    pinned = {
        "/a.png": Response(png_bytes(tmp_path)),
        "/b.jpg": Response(baseline_jpeg(tmp_path / "b.jpg").read_bytes()),
    }
    with serving(pinned) as origin:
        source = illustrated_source(tmp_path / "clip.md", f"{origin}/a.png", f"{origin}/b.jpg")
        refused = run_cli(
            "prepare", str(source), *PROFILE, "--output", str(tmp_path / "before.epub"), "--json"
        )
        document = localised(source, tmp_path / "repair")

    assert refused.returncode == 3
    assert json.loads(refused.stdout)["refusal"]["boundary"] == "image-processing-failure"
    assert document["outcome"] == "completed", document

    evidence = tmp_path / "repair"
    built = run_cli(
        "prepare",
        str(source),
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
    report = json.loads(built.stdout)
    assert report["outcome"] == "completed"
    assert report["preparation"]["images"]["totals"]["references"]["value"] == 3
    assert len(media_resources(tmp_path / "after.epub")) == 3


def test_the_rewritten_document_changes_image_locations_and_nothing_else(tmp_path: Path) -> None:
    """Repair validation accepts the emitted document because nothing it checks moved: the title,
    the author, the Pandoc API version, the baseline digest and every non-image node are the ones
    the inspection recorded, and only the `src` values are new."""

    with serving({"/a.png": Response(png_bytes(tmp_path))}) as origin:
        source = illustrated_source(tmp_path / "clip.md", f"{origin}/a.png")
        inspected = run_cli(
            "inspect",
            str(source),
            *PROFILE,
            "--json",
            "--evidence-dir",
            str(tmp_path / "inspected"),
        )
        document = localised(source, tmp_path / "repair")

    assert inspected.returncode == 0
    original = read_json(tmp_path / "inspected" / "canonical-document.json")
    rewritten = read_json(tmp_path / "repair" / "canonical-document.json")
    inspection = read_json(tmp_path / "repair" / "report.json")

    assert document["outcome"] == "completed"
    for field in ("schema", "title", "author", "source_url", "warnings"):
        assert rewritten[field] == original[field], field
    assert rewritten["pandoc"]["pandoc-api-version"] == original["pandoc"]["pandoc-api-version"]
    assert image_locators(rewritten) == [str(tmp_path / "repair" / "images" / "image-1.png")]
    assert image_locators(original) != image_locators(rewritten)
    assert blind_to_image_targets(rewritten) == blind_to_image_targets(original)
    assert (tmp_path / "repair" / "preservation-baseline.txt").read_bytes() == (
        tmp_path / "inspected" / "preservation-baseline.txt"
    ).read_bytes()
    assert inspection["galley"]["command"] == "localise"


def test_localise_writes_only_inside_its_evidence_directory_and_never_the_source(
    tmp_path: Path,
) -> None:
    """One explicit step with one place to put things: the Repair Set, the retrieved bytes, and
    nothing else on the machine. The source is read and left exactly as it was found."""

    workspace = tmp_path / "elsewhere"
    workspace.mkdir()
    with serving({"/a.png": Response(png_bytes(tmp_path))}) as origin:
        source = illustrated_source(workspace / "clip.md", f"{origin}/a.png")
        before = file_hashes(workspace)
        document = localised(source, tmp_path / "repair")

    assert document["outcome"] == "completed"
    assert file_hashes(workspace) == before
    assert sorted(
        str(path.relative_to(tmp_path / "repair")) for path in (tmp_path / "repair").rglob("*")
    ) == [
        "canonical-document.json",
        "images",
        "images/image-1.png",
        "preservation-baseline.txt",
        "report.json",
    ]


def test_the_document_records_each_reference_and_only_overwrite_replaces_a_repair_set(
    tmp_path: Path,
) -> None:
    """The record is the evidence: locator, host, resolved addresses, transport, and the digest,
    size and measured media type of what landed. A second run into the same directory refuses
    until it is given the one permission that replaces a command-owned output."""

    payload = png_bytes(tmp_path)
    with serving({"/a.png": Response(payload), "/b.png": Response(payload)}) as origin:
        source = illustrated_source(tmp_path / "clip.md", f"{origin}/a.png", f"{origin}/a.png")
        document = localised(source, tmp_path / "repair")
        again = localised(source, tmp_path / "repair")
        replaced = localised(source, tmp_path / "repair", overwrite=True)

    assert document["galley"]["document_schema"] == LOCALISATION_SCHEMA
    assert document["galley"]["command"] == "localise"
    assert len(document["references"]) == 1, "one locator referenced twice is one retrieval"
    reference = document["references"][0]
    assert reference["occurrences"] == 2
    assert reference["host"] == "127.0.0.1"
    assert reference["transport"] == {"outcome": "retrieved", "status": 200, "detail": ""}
    assert reference["media_type"] == "image/png"
    assert reference["byte_size"] == len(payload)
    assert reference["path"] == str(tmp_path / "repair" / "images" / "image-1.png")
    assert again["outcome"] == "refused"
    assert again["refusal"]["boundary"] == "output-exists"
    assert replaced["outcome"] == "completed"


def test_prepare_still_retrieves_nothing_and_rebuilds_the_same_bytes(tmp_path: Path) -> None:
    """The reason this is a command and not a flag. Once the images are local, two preparations
    from the same Repair Set produce byte-identical books — and the second one runs with the
    server gone, so nothing in `prepare` reached the network."""

    with serving({"/a.png": Response(png_bytes(tmp_path))}) as origin:
        source = illustrated_source(tmp_path / "clip.md", f"{origin}/a.png")
        document = localised(source, tmp_path / "repair")

    assert document["outcome"] == "completed"
    evidence = tmp_path / "repair"
    repair = (
        "--inspection-report",
        str(evidence / "report.json"),
        "--canonical-document",
        str(evidence / "canonical-document.json"),
        "--preservation-baseline",
        str(evidence / "preservation-baseline.txt"),
    )
    builds = [
        run_cli(
            "prepare",
            str(source),
            *PROFILE,
            "--output",
            str(tmp_path / f"book-{number}.epub"),
            "--json",
            *repair,
        )
        for number in range(2)
    ]

    assert all(build.returncode == 0 for build in builds), builds[0].stdout
    assert (tmp_path / "book-0.epub").read_bytes() == (tmp_path / "book-1.epub").read_bytes()


def test_a_localised_source_publishes_an_illustrated_ready_artifact(tmp_path: Path) -> None:
    """The Workspace path, which is what "Galley my inbox" actually runs: the Repair Set feeds a
    `prepare --ready` under the hash Inbox Check observed, and the immutable Ready Artifact that
    publishes carries the pictures."""

    workspace = tmp_path / "workspace"
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    with serving({"/a.png": Response(png_bytes(tmp_path))}) as origin:
        source = illustrated_source(inbox / "clip.md", f"{origin}/a.png")
        document = localised(source, tmp_path / "repair")

    assert document["outcome"] == "completed"
    evidence = tmp_path / "repair"
    published = run_cli(
        "prepare",
        str(source),
        *PROFILE,
        "--ready",
        "--json",
        "--expected-source-hash",
        sha256(source.read_bytes()).hexdigest(),
        "--inspection-report",
        str(evidence / "report.json"),
        "--canonical-document",
        str(evidence / "canonical-document.json"),
        "--preservation-baseline",
        str(evidence / "preservation-baseline.txt"),
        environment=workspace_environment(workspace, tmp_path / "home"),
    )

    assert published.returncode == 0, published.stdout
    report = json.loads(published.stdout)
    artifact = Path(str(report["artifact"]["path"]))
    assert artifact == workspace / "ready" / "An Illustrated Clipping.epub"
    assert len(media_resources(artifact)) == 2


def test_the_concise_rendering_states_the_repair_set_and_every_reference(tmp_path: Path) -> None:
    """Without `--json` a completed run prints the `prepare` invocation its Repair Set feeds, and
    one line per reference naming where the bytes came from and what they measured as."""

    with serving({"/a.png": Response(png_bytes(tmp_path))}) as origin:
        source = illustrated_source(tmp_path / "clip.md", f"{origin}/a.png")
        document = localised(source, tmp_path / "repair")
        locator = f"{origin}/a.png"

    rendered = render_localisation(document)

    assert rendered.startswith("localise: completed\nProfile: x4-crosspoint\n")
    assert f"Repair Set: {tmp_path / 'repair'}" in rendered
    assert f"--canonical-document {tmp_path / 'repair' / 'canonical-document.json'}" in rendered
    assert (
        f"image-1: {locator} (127.0.0.1 \u2192 127.0.0.1) \u2014 retrieved, image/png" in rendered
    )
    assert str(tmp_path / "repair" / "images" / "image-1.png") in rendered


def test_an_inline_reference_is_left_exactly_as_it_arrived(tmp_path: Path) -> None:
    """Localisation retrieves what is elsewhere. A picture already inside the document is not
    elsewhere, so it is neither retrieved, nor recorded as retrieved, nor rewritten."""

    inline = "data:image/png;base64," + b64encode(png_bytes(tmp_path, "inline.png")).decode()
    with serving({"/a.png": Response(png_bytes(tmp_path))}) as origin:
        source = illustrated_source(tmp_path / "mixed.md", inline, f"{origin}/a.png")
        document = localised(source, tmp_path / "repair")

    assert document["outcome"] == "completed"
    assert [entry["locator"] for entry in document["references"]] == [f"{origin}/a.png"]
    locators = image_locators(read_json(tmp_path / "repair" / "canonical-document.json"))
    assert locators[0] == inline
    assert locators[1].endswith(".png") and not locators[1].startswith("http")
