"""Check configured Inboxes read-only through the installed public CLI."""

from pathlib import Path

from tests.public_cli import run_public_cli
from tests.workspace_fixtures import (
    command_document,
    entries,
    field,
    inbox_table,
    tree,
    workspace_environment,
    write_configuration,
)

COMPLETED = 0
REFUSED = 3


def _inbox_workspace(root: Path, *tables: str) -> tuple[Path, dict[str, str]]:
    workspace = root / "workspace"
    _ = write_configuration(workspace, "version = 1\n\n" + "\n".join(tables))
    return workspace, workspace_environment(workspace, root / "home")


def _note(path: Path, body: str = "# Note\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(body, encoding="utf-8")
    return path


def test_inboxes_are_attempted_in_configured_order(tmp_path: Path) -> None:
    """Coverage names each Inbox's resolved path, recursion and exact counts, in order."""

    first = tmp_path / "first"
    second = tmp_path / "second"
    _ = _note(first / "a.md")
    _ = _note(second / "b.markdown")
    _ = _note(second / "notes.txt", "plain\n")
    _, environment = _inbox_workspace(
        tmp_path,
        inbox_table("second", str(second)),
        inbox_table("first", str(first), recursive=True),
    )
    for result in run_public_cli("inbox", "check", "--json", environment=environment):
        document = command_document(result)
        coverage = entries(document, "coverage")
        assert [entry["name"] for entry in coverage] == ["second", "first"]
        assert coverage[0]["resolved_path"] == str(second.resolve())
        assert coverage[0]["recursive"] is False
        assert coverage[0]["status"] == "checked"
        assert coverage[0]["supported_count"] == 1
        assert coverage[0]["ignored_count"] == 1
        assert coverage[1]["recursive"] is True
        assert result.returncode == COMPLETED


def test_recursion_is_configured_per_inbox(tmp_path: Path) -> None:
    """A non-recursive Inbox sees direct children only; a recursive one descends."""

    flat = tmp_path / "flat"
    nested = tmp_path / "nested"
    _ = _note(flat / "top.md")
    _ = _note(flat / "deeper" / "buried.md")
    _ = _note(nested / "top.md")
    _ = _note(nested / "deeper" / "buried.md")
    _, environment = _inbox_workspace(
        tmp_path,
        inbox_table("flat", str(flat)),
        inbox_table("nested", str(nested), recursive=True),
    )
    for result in run_public_cli("inbox", "check", "--json", environment=environment):
        document = command_document(result)
        coverage = entries(document, "coverage")
        assert coverage[0]["supported_count"] == 1
        assert coverage[1]["supported_count"] == 2
        found = {
            Path(str(entry["resolved_path"])).name for entry in entries(document, "candidates")
        }
        assert found == {"top.md", "buried.md"}


def test_directory_symlinks_are_never_followed(tmp_path: Path) -> None:
    """A recursive Inbox descends ordinary directories only, so it cannot walk out of itself."""

    inbox = tmp_path / "inbox"
    outside = tmp_path / "outside"
    _ = _note(inbox / "inside.md")
    _ = _note(outside / "elsewhere.md")
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "link").symlink_to(outside, target_is_directory=True)
    _, environment = _inbox_workspace(tmp_path, inbox_table("inbox", str(inbox), recursive=True))
    for result in run_public_cli("inbox", "check", "--json", environment=environment):
        candidates = entries(command_document(result), "candidates")
        assert [Path(str(entry["resolved_path"])).name for entry in candidates] == ["inside.md"]


def test_hidden_entries_and_unsupported_files_never_become_candidates(tmp_path: Path) -> None:
    """Hidden entries are ignored outright; visible unsupported files raise the ignored count."""

    inbox = tmp_path / "inbox"
    _ = _note(inbox / "kept.md")
    _ = _note(inbox / ".hidden.md")
    _ = _note(inbox / ".hidden" / "buried.md")
    _ = _note(inbox / "page.html", "<p>x</p>\n")
    _ = _note(inbox / "book.epub", "not really\n")
    _, environment = _inbox_workspace(tmp_path, inbox_table("inbox", str(inbox), recursive=True))
    for result in run_public_cli("inbox", "check", "--json", environment=environment):
        document = command_document(result)
        coverage = entries(document, "coverage")
        assert coverage[0]["supported_count"] == 1
        assert coverage[0]["ignored_count"] == 2
        candidates = entries(document, "candidates")
        assert [Path(str(entry["resolved_path"])).name for entry in candidates] == ["kept.md"]


def test_each_candidate_states_its_full_identity(tmp_path: Path) -> None:
    """A candidate carries the paths, kind, size, modification time and hash that identify it."""

    inbox = tmp_path / "inbox"
    source = _note(inbox / "note.md", "# Heading\n\nBody.\n")
    _, environment = _inbox_workspace(tmp_path, inbox_table("inbox", str(inbox)))
    for result in run_public_cli("inbox", "check", "--json", environment=environment):
        candidate = entries(command_document(result), "candidates")[0]
        assert candidate["primary_inbox"] == "inbox"
        assert candidate["inboxes"] == ["inbox"]
        assert candidate["display_path"] == str(source.resolve())
        assert candidate["resolved_path"] == str(source.resolve())
        assert candidate["source_kind"] == "markdown"
        assert candidate["byte_size"] == source.stat().st_size
        assert str(candidate["modified_at"]).endswith("Z")
        assert len(str(candidate["sha256"])) == 64


def test_overlapping_inboxes_deduplicate_by_resolved_path(tmp_path: Path) -> None:
    """One source two roots can see is one candidate, owned by the first configured Inbox."""

    outer = tmp_path / "outer"
    inner = outer / "inner"
    _ = _note(inner / "shared.md")
    _, environment = _inbox_workspace(
        tmp_path,
        inbox_table("outer", str(outer), recursive=True),
        inbox_table("inner", str(inner)),
    )
    for result in run_public_cli("inbox", "check", "--json", environment=environment):
        document = command_document(result)
        candidates = entries(document, "candidates")
        assert len(candidates) == 1
        assert candidates[0]["primary_inbox"] == "outer"
        assert candidates[0]["inboxes"] == ["outer", "inner"]
        coverage = entries(document, "coverage")
        assert [entry["supported_count"] for entry in coverage] == [1, 1]


def test_an_unavailable_inbox_does_not_block_a_healthy_one(tmp_path: Path) -> None:
    """A missing volume is reported as unavailable and never read as completed coverage."""

    healthy = tmp_path / "healthy"
    _ = _note(healthy / "kept.md")
    _, environment = _inbox_workspace(
        tmp_path,
        inbox_table("missing", str(tmp_path / "absent")),
        inbox_table("healthy", str(healthy)),
    )
    for result in run_public_cli("inbox", "check", "--json", environment=environment):
        document = command_document(result)
        coverage = entries(document, "coverage")
        assert coverage[0]["status"] == "unavailable"
        assert "absent" in str(coverage[0]["error"])
        assert coverage[1]["status"] == "checked"
        assert len(entries(document, "candidates")) == 1
        assert result.returncode == COMPLETED


def test_ordering_is_stable_and_never_selects_on_a_display_name(tmp_path: Path) -> None:
    """Two files sharing a basename both survive; ordering is Inbox order then resolved path."""

    first = tmp_path / "first"
    second = tmp_path / "second"
    _ = _note(first / "note.md", "first\n")
    _ = _note(first / "alpha.md", "alpha\n")
    _ = _note(second / "note.md", "second\n")
    _, environment = _inbox_workspace(
        tmp_path,
        inbox_table("first", str(first)),
        inbox_table("second", str(second)),
    )
    for result in run_public_cli("inbox", "check", "--json", environment=environment):
        candidates = entries(command_document(result), "candidates")
        assert [entry["resolved_path"] for entry in candidates] == [
            str((first / "alpha.md").resolve()),
            str((first / "note.md").resolve()),
            str((second / "note.md").resolve()),
        ]


def test_the_check_creates_nothing_and_changes_nothing(tmp_path: Path) -> None:
    """No watcher, queue, index or work artifact: the tree is byte-identical afterwards."""

    inbox = tmp_path / "inbox"
    _ = _note(inbox / "note.md")
    _ = _note(inbox / "other.txt", "plain\n")
    _, environment = _inbox_workspace(tmp_path, inbox_table("inbox", str(inbox), recursive=True))
    before = tree(tmp_path)
    for result in run_public_cli("inbox", "check", "--json", environment=environment):
        assert result.returncode == COMPLETED
    assert tree(tmp_path) == before


def test_a_broken_configuration_refuses_before_any_inbox_is_read(tmp_path: Path) -> None:
    """Inbox Check consumes validated configuration and refuses at the same boundaries."""

    workspace = tmp_path / "workspace"
    _ = write_configuration(workspace, "version = 3\n")
    environment = workspace_environment(workspace, tmp_path / "home")
    for result in run_public_cli("inbox", "check", "--json", environment=environment):
        document = command_document(result)
        refusal = field(document, "refusal")
        assert refusal["boundary"] == "unsupported-configuration-version"
        assert refusal["authority"] == "inbox check"
        assert entries(document, "coverage") == []
        assert result.returncode == REFUSED


def test_human_output_states_the_same_facts_as_the_document(tmp_path: Path) -> None:
    """Concise output is rendered from the document rather than assembled separately."""

    inbox = tmp_path / "inbox"
    source = _note(inbox / "note.md")
    _, environment = _inbox_workspace(tmp_path, inbox_table("inbox", str(inbox)))
    for result in run_public_cli("inbox", "check", environment=environment):
        assert result.stdout.startswith("inbox check: completed\n")
        assert "Inbox inbox: checked (direct children) — 1 supported, 0 ignored" in result.stdout
        assert "Candidates: 1" in result.stdout
        assert str(source.resolve()) in result.stdout
        assert result.returncode == COMPLETED


def test_a_file_symlink_is_one_candidate_with_its_target(tmp_path: Path) -> None:
    """Identity is the resolved path, so a link and its target are one source, not two."""

    inbox = tmp_path / "inbox"
    target = _note(inbox / "real.md")
    (inbox / "link.md").symlink_to(target)
    _, environment = _inbox_workspace(tmp_path, inbox_table("inbox", str(inbox)))
    for result in run_public_cli("inbox", "check", "--json", environment=environment):
        candidates = entries(command_document(result), "candidates")
        assert len(candidates) == 1
        assert candidates[0]["display_path"] == str(
            (inbox / "link.md").resolve().parent / "link.md"
        )
        assert candidates[0]["resolved_path"] == str(target.resolve())


def test_a_subdirectory_it_cannot_list_makes_the_inbox_unavailable(tmp_path: Path) -> None:
    """Partial descent is never reported as a completed check, and loses no observed candidate."""

    inbox = tmp_path / "inbox"
    _ = _note(inbox / "visible.md")
    locked = inbox / "locked"
    locked.mkdir(parents=True)
    _ = _note(locked / "buried.md")
    locked.chmod(0o000)
    _, environment = _inbox_workspace(tmp_path, inbox_table("inbox", str(inbox), recursive=True))
    try:
        for result in run_public_cli("inbox", "check", "--json", environment=environment):
            document = command_document(result)
            coverage = entries(document, "coverage")
            assert coverage[0]["status"] == "unavailable"
            assert str(locked.resolve()) in str(coverage[0]["error"])
            assert len(entries(document, "candidates")) == 1
            assert result.returncode == COMPLETED
    finally:
        locked.chmod(0o700)
