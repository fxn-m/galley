"""Publish portable, human-readable Ready Artifact names through the installed CLI."""

from pathlib import Path

from tests.ready_fixtures import (
    prepare_ready,
    BODY,
    COMPLETED,
    PROFILE,
    facts,
    inbox_note,
    ready_reports,
    report,
)
from tests.workspace_fixtures import workspace_environment

READY_ARGUMENTS = ("--profile", PROFILE, "--ready", "--json")


def test_ready_name_preserves_ordinary_title_spaces(tmp_path: Path) -> None:
    """A Ready Artifact uses the book title as its portable filename."""

    source = inbox_note(
        tmp_path,
        body="---\ntitle: A Plain Book\n---\n\nA short body with enough words to prepare.\n",
    )
    workspace = tmp_path / "workspace"
    environment = workspace_environment(workspace, tmp_path / "home")
    result = prepare_ready(source, environment)
    assert result.returncode == COMPLETED
    published = Path(str(facts(report(result.stdout), "artifact")["path"]))
    assert published == workspace / "ready" / "A Plain Book.epub"


def test_ready_name_preserves_unicode_and_portable_punctuation(tmp_path: Path) -> None:
    """NFC letters, numbers and the complete portable punctuation set survive."""

    source = inbox_note(
        tmp_path,
        body=(
            '---\ntitle: "Cafe\u0301\'s, 2026 (\u7b2c2\u7248) [A&B] - draft_v1.2"\n---\n\n'
            "A short body with enough words to prepare.\n"
        ),
    )
    expected = "Caf\u00e9’s, 2026 (\u7b2c2\u7248) [A&B] - draft_v1.2.epub"
    workspace = tmp_path / "workspace"
    environment = workspace_environment(workspace, tmp_path / "home")
    result = prepare_ready(source, environment)
    assert result.returncode == COMPLETED
    published = Path(str(facts(report(result.stdout), "artifact")["path"]))
    assert published.name == expected


def test_ready_name_uses_an_eighty_byte_stem_without_splitting_unicode(tmp_path: Path) -> None:
    """The portable stem budget counts encoded bytes and keeps only complete characters."""

    title = "é" * 41
    source = inbox_note(
        tmp_path,
        body=f'---\ntitle: "{title}"\n---\n\nA short body with enough words to prepare.\n',
    )
    workspace = tmp_path / "workspace"
    environment = workspace_environment(workspace, tmp_path / "home")
    result = prepare_ready(source, environment)
    assert result.returncode == COMPLETED
    published = Path(str(facts(report(result.stdout), "artifact")["path"]))
    assert published.stem == "é" * 40
    assert len(published.stem.encode("utf-8")) == 80


def test_colliding_ready_name_reserves_its_digest_inside_the_byte_budget(
    tmp_path: Path,
) -> None:
    """Distinct bytes keep deterministic identity without lengthening the portable stem."""

    title = "é" * 50
    first_source = inbox_note(
        tmp_path,
        "first.md",
        f'---\ntitle: "{title}"\n---\n\nThe first book has enough words to prepare.\n',
    )
    second_source = inbox_note(
        tmp_path,
        "second.md",
        f'---\ntitle: "{title}"\n---\n\nThe second book has different words to prepare.\n',
    )
    workspace = tmp_path / "workspace"
    environment = workspace_environment(workspace, tmp_path / "home")
    first = prepare_ready(first_source, environment)
    assert first.returncode == COMPLETED
    original = Path(str(facts(report(first.stdout), "artifact")["path"]))
    original_bytes = original.read_bytes()
    second = prepare_ready(second_source, environment)
    assert second.returncode == COMPLETED
    second_artifact = facts(report(second.stdout), "artifact")
    colliding = Path(str(second_artifact["path"]))
    assert colliding.stem == f"{'é' * 33}-{str(second_artifact['sha256'])[:12]}"
    assert len(colliding.stem.encode("utf-8")) <= 80
    assert original.read_bytes() == original_bytes


def test_ready_name_turns_unsafe_characters_into_normalised_separators(tmp_path: Path) -> None:
    """Filesystem, multipart and control hazards separate rather than join title words."""

    source = inbox_note(
        tmp_path,
        ' .  Alpha\\Beta:Gamma"Delta"<Epsilon>?*| \t Zeta\x7fEta . .md',
    )
    workspace = tmp_path / "workspace"
    environment = workspace_environment(workspace, tmp_path / "home")
    result = prepare_ready(source, environment)
    assert result.returncode == COMPLETED
    published = Path(str(facts(report(result.stdout), "artifact")["path"]))
    assert published.name == "Alpha Beta Gamma Delta Epsilon Zeta Eta.epub"

    slash_source = inbox_note(
        tmp_path,
        "slash.md",
        body='---\ntitle: "Forward/Slash"\n---\n\nA short body with enough words to prepare.\n',
    )
    slash_result = prepare_ready(slash_source, environment)
    assert slash_result.returncode == COMPLETED
    slash_artifact = Path(str(facts(report(slash_result.stdout), "artifact")["path"]))
    assert slash_artifact.name == "Forward Slash.epub"


def test_ready_name_uses_the_stable_fallback_when_nothing_survives(tmp_path: Path) -> None:
    """A title made only of separators and unsafe characters still publishes predictably."""

    source = inbox_note(tmp_path, "... ☃ ....md")
    workspace = tmp_path / "workspace"
    environment = workspace_environment(workspace, tmp_path / "home")
    result = prepare_ready(source, environment)
    assert result.returncode == COMPLETED
    published = Path(str(facts(report(result.stdout), "artifact")["path"]))
    assert published.name == "book.epub"


def test_identical_bytes_are_reused_with_their_own_evidence(tmp_path: Path) -> None:
    """Identical-byte sources reuse the artifact without rewriting and retain separate Reports."""

    first_source = inbox_note(tmp_path, "note.md")
    copied = tmp_path / "elsewhere" / "note.md"
    copied.parent.mkdir(parents=True)
    _ = copied.write_text(BODY, encoding="utf-8")
    workspace = tmp_path / "workspace"
    environment = workspace_environment(workspace, tmp_path / "home")
    first = prepare_ready(first_source, environment)
    assert first.returncode == COMPLETED
    published = Path(str(facts(report(first.stdout), "artifact")["path"]))
    stamp = published.stat().st_mtime_ns
    second = prepare_ready(copied, environment)
    assert second.returncode == COMPLETED
    assert Path(str(facts(report(second.stdout), "artifact")["path"])) == published
    assert published.stat().st_mtime_ns == stamp
    reports = ready_reports(workspace)
    assert len(reports) == 2
    assert {str(facts(retained, "source")["path"]) for retained in reports} == {
        str(first_source.resolve()),
        str(copied.resolve()),
    }
