"""Publish immutable Ready Artifacts through the installed public CLI."""

from hashlib import sha256
from pathlib import Path

from tests.support.article_fixtures import ARTICLE
from tests.support.article_server import served
from tests.support.public_cli import run_cli
from tests.support.ready_fixtures import (
    BODY,
    COMPLETED,
    PROFILE,
    facts,
    inbox_note,
    prepare_ready,
    ready_reports,
    report,
)
from tests.support.workspace_fixtures import tree, workspace_environment


def test_ready_publishes_the_artifact_and_its_evidence(tmp_path: Path) -> None:
    """A checked Markdown candidate becomes a Ready Artifact with an immutable Report."""

    source = inbox_note(tmp_path)
    workspace = tmp_path / "workspace"
    environment = workspace_environment(workspace, tmp_path / "home")
    before = tree(tmp_path / "inbox")
    digest = sha256(source.read_bytes()).hexdigest()
    first = prepare_ready(source, environment)
    assert first.returncode == COMPLETED
    published_report = report(first.stdout)
    artifact = facts(published_report, "artifact")
    published = Path(str(artifact["path"]))
    assert published == workspace / "ready" / "note.epub"
    assert published.is_file()
    assert sha256(published.read_bytes()).hexdigest() == artifact["sha256"]
    retained = ready_reports(workspace)
    assert len(retained) == 1
    assert facts(retained[0], "source")["path"] == str(source.resolve())
    assert facts(retained[0], "source")["sha256"] == facts(published_report, "source")["sha256"]
    assert facts(retained[0], "profile")["id"] == PROFILE
    assert facts(retained[0], "artifact")["path"] == str(published)

    assert published_report["compatibility"]
    assert "text_preservation" in artifact
    assert "conformance" in artifact
    assert facts(published_report, "preparation")["images"] is not None

    assert published_report["reading_verdict"] == {"value": "not_tested", "predicted": None}

    assert tree(tmp_path / "inbox") == before
    assert sha256(source.read_bytes()).hexdigest() == digest

    identity = facts(facts(published_report, "preparation"), "artifact_identity")
    canonical = facts(published_report, "canonical_document")
    assert identity["identifier"] == f"urn:sha256:{canonical['sha256']}"
    assert identity["source_date_epoch"] == "0"


def test_different_bytes_take_a_deterministic_hash_suffix(tmp_path: Path) -> None:
    """A second distinct book competing for one name never replaces the first."""

    source = inbox_note(tmp_path)
    workspace = tmp_path / "workspace"
    environment = workspace_environment(workspace, tmp_path / "home")
    first = prepare_ready(source, environment)
    original = Path(str(facts(report(first.stdout), "artifact")["path"])).read_bytes()
    _ = source.write_text(BODY + "\nAn added paragraph that changes the book.\n", encoding="utf-8")
    second = prepare_ready(source, environment)
    assert second.returncode == COMPLETED
    published = Path(str(facts(report(second.stdout), "artifact")["path"]))
    assert published.name.startswith("note-")
    assert published != workspace / "ready" / "note.epub"
    assert (workspace / "ready" / "note.epub").read_bytes() == original
    assert len(ready_reports(workspace)) == 2


def test_an_explicit_output_still_behaves_exactly_as_before(tmp_path: Path) -> None:
    """The named-output mode is unchanged, including its companion evidence directory."""

    source = inbox_note(tmp_path)
    output = tmp_path / "book0.epub"
    result = run_cli(
        "prepare", str(source), "--profile", PROFILE, "--output", str(output), "--json"
    )
    assert result.returncode == COMPLETED
    assert output.is_file()
    assert (tmp_path / "book0.galley" / "report.json").is_file()


def test_two_runs_over_identical_bytes_produce_identical_artifacts(tmp_path: Path) -> None:
    """Identical-byte reuse is only meaningful because preparation is reproducible."""

    source = inbox_note(tmp_path)
    digests: list[str] = []
    for index in range(2):
        output = tmp_path / f"book{index}.epub"
        result = run_cli(
            "prepare", str(source), "--profile", PROFILE, "--output", str(output), "--json"
        )
        assert result.returncode == COMPLETED
        digests.append(sha256(output.read_bytes()).hexdigest())
    assert digests[0] == digests[1]


def test_an_article_like_page_publishes_as_a_ready_artifact(tmp_path: Path) -> None:
    """Both supported source kinds reach Ready publication through the same pipeline."""

    workspace = tmp_path / "workspace"
    environment = workspace_environment(workspace, tmp_path / "home")
    with served(ARTICLE) as url:
        result = run_cli(
            "prepare", url, "--profile", PROFILE, "--ready", "--json", environment=environment
        )
    assert result.returncode == COMPLETED
    published_report = report(result.stdout)
    published = Path(str(facts(published_report, "artifact")["path"]))
    assert published.parent == workspace / "ready"
    assert published.is_file()
    retained = ready_reports(workspace)
    assert len(retained) == 1
    assert facts(retained[0], "source")["url"] == url
    assert (published.parent / "evidence").is_dir()
