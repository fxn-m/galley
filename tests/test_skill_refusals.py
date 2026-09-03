"""Refuse a skill installation Galley cannot account for, having changed nothing.

Installation is the one thing Galley writes into a directory it does not own, so a destination it
cannot attribute to an installation of its own is a conflict a person has to authorise rather than
something to overwrite. Every test here asserts the target is byte-for-byte what it was.
"""

from pathlib import Path

from tests.public_cli import run_cli
from tests.skill_fixtures import (
    contents,
    differences,
    document_of,
    foreign_skill,
    isolated_home,
    no_staging_left,
    refusal_fact,
    refusal_of,
    skill_entries,
)

COMPLETED = 0
REFUSED = 3
CONFLICT = "unattributable-skill-destination"


def _install(target: Path, *arguments: str, home: Path) -> dict[str, object]:
    """Install through the first public entry point, returning the document it emitted."""

    documents: list[dict[str, object]] = []
    result = run_cli(
        "skill",
        "install",
        "--target",
        str(target),
        *arguments,
        "--json",
        environment=isolated_home(home),
    )
    documents.append(document_of(result))
    documents[-1]["exit_code"] = result.returncode
    return documents[0]


def test_a_foreign_destination_refuses_without_touching_the_target(tmp_path: Path) -> None:
    """A destination carrying no Galley manifest is somebody else's, and stops the install."""

    target = tmp_path / "target"
    before = foreign_skill(target, "galley")

    document = _install(target, home=tmp_path / "home")
    entries = skill_entries(document)

    assert document["exit_code"] == REFUSED
    assert refusal_of(document)["boundary"] == CONFLICT
    assert entries["galley"]["state"] == "foreign"
    assert [entry["action"] for entry in entries.values()] == ["skipped", "skipped"]
    assert contents(target) == before
    assert no_staging_left(target)


def test_a_missing_managed_file_refuses_and_names_it(tmp_path: Path) -> None:
    """An installation Galley can no longer account for is not replaced by default."""

    target = tmp_path / "target"
    home = tmp_path / "home"
    _ = _install(target, home=home)
    (target / "galley" / "resources" / "report-fields.md").unlink()
    before = contents(target)

    document = _install(target, home=home)

    assert document["exit_code"] == REFUSED
    assert skill_entries(document)["galley"]["state"] == "modified"
    assert "resources/report-fields.md" in str(refusal_fact(document)["destinations"])
    assert contents(target) == before


def test_a_local_change_and_an_untracked_file_both_refuse(tmp_path: Path) -> None:
    """A managed directory has to match its manifest exactly: an addition counts as a change.

    An untracked addition deliberately counts as a local change: an upgrade replaces the whole
    directory, so a file Galley cannot attribute to itself would be deleted by a run the user
    asked to update a skill.
    """

    for name, change in (("edited", _edit), ("added", _add)):
        target = tmp_path / name
        home = tmp_path / "home"
        _ = _install(target, home=home)
        change(target)
        before = contents(target)

        document = _install(target, home=home)

        assert document["exit_code"] == REFUSED
        assert skill_entries(document)["galley"]["state"] == "modified"
        assert contents(target) == before
        assert no_staging_left(target)


def test_a_forced_run_states_in_its_own_document_which_conflict_it_overruled(
    tmp_path: Path,
) -> None:
    """Force replaces the two named directories "after reporting the conflict", so it reports it."""

    target = tmp_path / "target"
    home = tmp_path / "home"
    _ = _install(target, home=home)
    _edit(target)
    _ = (target / "galley" / "resources" / "mine.md").write_text("mine\n", encoding="utf-8")

    refused = _install(target, home=home)
    forced = _install(target, "--force", home=home)
    entries = skill_entries(forced)

    assert refused["exit_code"] == REFUSED
    assert differences(skill_entries(refused)["galley"]) == [
        "SKILL.md",
        "resources/mine.md",
    ]
    assert forced["exit_code"] == COMPLETED
    assert entries["galley"]["action"] == "replaced"
    assert differences(entries["galley"]) == ["SKILL.md", "resources/mine.md"]
    assert differences(entries["galley-setup"]) == []
    assert not (target / "galley" / "resources" / "mine.md").exists()


def test_a_target_occupied_by_a_file_refuses_before_writing(tmp_path: Path) -> None:
    """A target that cannot hold an installation is refused while nothing has been attempted."""

    target = tmp_path / "occupied"
    _ = target.write_text("not a directory\n", encoding="utf-8")

    document = _install(target, home=tmp_path / "home")

    assert document["exit_code"] == REFUSED
    assert refusal_of(document)["boundary"] == "skill-target-unusable"
    assert target.read_text(encoding="utf-8") == "not a directory\n"


def _edit(target: Path) -> None:
    path = target / "galley" / "SKILL.md"
    _ = path.write_text(path.read_text(encoding="utf-8") + "\nlocal note\n", encoding="utf-8")


def _add(target: Path) -> None:
    _ = (target / "galley" / "resources" / "mine.md").write_text("mine\n", encoding="utf-8")


def test_the_human_rendering_names_the_boundary_and_what_differed(tmp_path: Path) -> None:
    """Concise output is the same document, so it carries the detail a person acts on."""

    target = tmp_path / "target"
    home = tmp_path / "home"
    assert _install(target, home=home)["exit_code"] == COMPLETED
    _edit(target)

    result = run_cli("skill", "install", "--target", str(target), environment=isolated_home(home))
    assert result.returncode == REFUSED
    assert f"Boundary: {CONFLICT}" in result.stdout
    assert "differs: SKILL.md" in result.stdout
