import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from tests.support.markdown_fixtures import (
    RETAINED_EVIDENCE_BASELINE,
    UNTITLED,
    write_markdown,
)
from tests.support.public_cli import NO_PANDOC, run_cli
from tests.support.report_fixtures import X4_PROFILE_FACTS


def inspect_json(source: Path, *extra: str) -> Any:
    result = run_cli("inspect", str(source), "--profile", "x4-crosspoint", "--json", *extra)
    assert (result.returncode, result.stderr) == (0, "")
    return json.loads(result.stdout)


def test_inspect_reports_source_and_canonical_document_facts(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "retained.md")
    original = source.read_bytes()

    report = inspect_json(source)
    assert report["galley"]["command"] == "inspect"
    assert (report["outcome"], report["refusal"]) == ("completed", None)
    assert report["profile"] == X4_PROFILE_FACTS
    assert report["galley"]["dependencies"]["pandoc"] == "3.10"
    assert report["source"] == {
        "byte_size": {"basis": "measured", "unit": "bytes", "value": len(original)},
        "encoding": "utf-8",
        "kind": "markdown",
        "parser": {
            "matches_pinned_version": True,
            "pinned_version": "3.10",
            "reader": "markdown",
            "tool": "pandoc",
            "version": "3.10",
        },
        "path": str(source.resolve()),
        "sha256": sha256(original).hexdigest(),
    }
    canonical = report["canonical_document"]
    assert canonical["schema"] == "galley/canonical-document/1"
    assert canonical["title"] == "Retained Evidence"
    assert canonical["title_source"] == "metadata"
    assert canonical["author"] == "Ada Lovelace"
    assert canonical["source_url"] is None
    assert canonical["pandoc_api_version"] == "1.23.1.2"
    assert canonical["blocks"] == {"basis": "measured", "unit": "blocks", "value": 4}
    baseline = RETAINED_EVIDENCE_BASELINE.encode("utf-8")
    assert canonical["preservation_baseline"] == {
        "byte_size": {"basis": "measured", "unit": "bytes", "value": len(baseline)},
        "encoding": "utf-8",
        "segments": {"basis": "measured", "unit": "segments", "value": 5},
        "sha256": sha256(baseline).hexdigest(),
    }
    assert source.read_bytes() == original


def test_inspect_leaves_stages_it_never_reached_truthfully_null(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "retained.md")

    report = inspect_json(source)
    assert report["extraction"] is None
    assert report["preparation"] is None
    assert report["artifact"] is None
    assert report["warnings"] == []
    assert report["reading_verdict"] == {"predicted": None, "value": "not_tested"}


def test_inspect_accepts_both_markdown_extensions(tmp_path: Path) -> None:
    short = write_markdown(tmp_path / "short.md")
    long_form = write_markdown(tmp_path / "long.markdown")
    upper = write_markdown(tmp_path / "upper.MD")

    for source in (short, long_form, upper):
        report = inspect_json(source)
        assert report["source"]["kind"] == "markdown"
        assert report["source"]["path"] == str(source.resolve())


def test_untitled_markdown_takes_its_title_from_the_source_stem(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "a plain note.md", UNTITLED)

    report = inspect_json(source)
    canonical = report["canonical_document"]
    assert canonical["title"] == "a plain note"
    assert canonical["title_source"] == "filename"
    assert canonical["author"] is None


def test_unreadable_source_refuses_without_reaching_a_canonical_document(tmp_path: Path) -> None:
    missing = tmp_path / "absent.md"

    result = run_cli("inspect", str(missing), "--profile", "x4-crosspoint", "--json")

    assert (result.returncode, result.stderr) == (3, "")
    report = json.loads(result.stdout)
    assert report["outcome"] == "refused"
    refusal = report["refusal"]
    assert refusal["boundary"] == "unreadable-source"
    assert refusal["stage"] == "source-acquisition"
    assert refusal["authority"] == "inspect"
    assert refusal["artifact_written"] is False
    assert refusal["fact"]["reason"] == "not-found"
    assert refusal["fact"]["path"] == str(missing.resolve())
    assert report["source"]["path"] == str(missing.resolve())
    assert report["canonical_document"] is None


def test_non_utf8_source_refuses_as_an_unreadable_source(tmp_path: Path) -> None:
    source = tmp_path / "latin.md"
    original = b"Caf\xe9 latin-1 bytes are not a Galley source.\n"
    _ = source.write_bytes(original)

    result = run_cli("inspect", str(source), "--profile", "x4-crosspoint", "--json")

    assert (result.returncode, result.stderr) == (3, "")
    refusal = json.loads(result.stdout)["refusal"]
    assert refusal["boundary"] == "unreadable-source"
    assert refusal["fact"]["reason"] == "not-utf8"
    assert source.read_bytes() == original


def test_missing_pandoc_refuses_at_the_dependency_boundary(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "retained.md")
    original = source.read_bytes()

    result = run_cli(
        "inspect",
        str(source),
        "--profile",
        "x4-crosspoint",
        "--json",
        environment=NO_PANDOC,
    )

    assert (result.returncode, result.stderr) == (3, "")
    report = json.loads(result.stdout)
    refusal = report["refusal"]
    assert refusal["boundary"] == "dependency-unavailable"
    assert refusal["stage"] == "source-parse"
    assert refusal["fact"] == {
        "detail": "the command was not found: galley-pandoc-not-installed",
        "pinned_version": "3.10",
        "reason": "not-found",
        "tool": "galley-pandoc-not-installed",
    }
    assert report["source"]["sha256"] == sha256(original).hexdigest()
    assert report["canonical_document"] is None
    assert source.read_bytes() == original


def test_human_inspect_output_renders_the_same_report(tmp_path: Path) -> None:
    source = write_markdown(tmp_path / "retained.md")
    original = source.read_bytes()
    baseline = RETAINED_EVIDENCE_BASELINE.encode("utf-8")

    result = run_cli("inspect", str(source), "--profile", "x4-crosspoint")

    expected = (
        "inspect: completed\n"
        "Profile: x4-crosspoint 0.4.0 (firmware 1.4.1)\n"
        f"Source: {source.resolve()} (markdown, utf-8)\n"
        f"Bytes: {len(original)}; sha256 {sha256(original).hexdigest()}\n"
        'Canonical Document: "Retained Evidence" by Ada Lovelace\n'
        "Pandoc AST 1.23.1.2; blocks: 4; constructor kinds: 9\n"
        "Unsupported Content: none (galley/modelled-set/1)\n"
        f"Preservation Baseline: segments 5; bytes {len(baseline)}; "
        f"sha256 {sha256(baseline).hexdigest()}\n"
        "Compatibility: true 0, false 0, unknown 4, unevaluable 1, not_applicable 2\n"
        "Projected, not measured: anchors-per-chapter 1 anchors (indeterminate)\n"
        "Observations: 13 recorded; 10 applicable; 0 fired; "
        "7 awaiting agent or human judgement\n"
    )
    assert (result.returncode, result.stdout, result.stderr) == (0, expected, "")
