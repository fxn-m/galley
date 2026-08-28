"""Remove Galley's Agent Skills through the installed public CLI, and nothing else.

Uninstall is the half of the lifecycle that force cannot reach. Every assertion here is about the
line between the two: files whose bytes are still the ones the manifest recorded go, and every
edited, added and foreign file stays and is reported.
"""

from pathlib import Path

from tests.public_cli import run_public_cli
from tests.skill_fixtures import (
    MANIFEST,
    SKILLS,
    contents,
    dispositions,
    document_of,
    foreign_skill,
    isolated_home,
    packaged_files,
    refusal_of,
    skill_entries,
)

COMPLETED = 0
REFUSED = 3


def _run(command: str, target: Path, home: Path, *arguments: str) -> dict[str, object]:
    documents: list[dict[str, object]] = []
    for result in run_public_cli(
        "skill",
        command,
        "--target",
        str(target),
        *arguments,
        "--json",
        environment=isolated_home(home),
    ):
        documents.append(document_of(result))
        documents[-1]["exit_code"] = result.returncode
    return documents[0]


def _installed(target: Path, home: Path) -> None:
    document = _run("install", target, home)
    assert document["exit_code"] == COMPLETED


def test_uninstall_removes_a_managed_installation_completely(tmp_path: Path) -> None:
    """Every file the manifest speaks for goes, and so does the directory holding them."""

    target = tmp_path / "target"
    home = tmp_path / "home"
    _installed(target, home)

    document = _run("uninstall", target, home)
    entries = skill_entries(document)

    assert document["exit_code"] == COMPLETED
    assert [entry["action"] for entry in entries.values()] == ["removed", "removed"]
    assert set(dispositions(entries["galley"]).values()) == {"removed"}
    assert set(dispositions(entries["galley"])) == set(packaged_files("galley"))
    assert contents(target) == {}
    assert target.is_dir()
    for skill in SKILLS:
        assert not (target / skill).exists()


def test_uninstall_retains_every_file_it_cannot_attribute_to_galley(tmp_path: Path) -> None:
    """An edited file, an added file and the directory holding them all survive."""

    target = tmp_path / "target"
    home = tmp_path / "home"
    _installed(target, home)
    edited = target / "galley" / "SKILL.md"
    _ = edited.write_text(edited.read_text(encoding="utf-8") + "\nmine\n", encoding="utf-8")
    added = target / "galley" / "resources" / "notes.md"
    _ = added.write_text("mine\n", encoding="utf-8")

    document = _run("uninstall", target, home)
    entries = skill_entries(document)
    reported = dispositions(entries["galley"])

    assert document["exit_code"] == COMPLETED
    assert entries["galley"]["action"] == "retained"
    assert entries["galley"]["state"] == "modified"
    assert entries["galley-setup"]["action"] == "removed"
    assert reported["SKILL.md"] == "retained"
    assert reported["resources/notes.md"] == "retained"
    assert reported["resources/cli-contract.md"] == "removed"
    assert edited.is_file() and added.is_file()
    assert not (target / "galley" / "resources" / "cli-contract.md").exists()
    assert not (target / "galley" / MANIFEST).exists()


def test_a_second_uninstall_finds_nothing_left_to_remove(tmp_path: Path) -> None:
    """Removal is idempotent: the second run reports an absent destination and stops."""

    target = tmp_path / "target"
    home = tmp_path / "home"
    _installed(target, home)
    _ = _run("uninstall", target, home)

    document = _run("uninstall", target, home)
    entries = skill_entries(document)

    assert document["exit_code"] == COMPLETED
    assert [entry["action"] for entry in entries.values()] == ["unchanged", "unchanged"]
    assert [entry["state"] for entry in entries.values()] == ["absent", "absent"]
    assert contents(target) == {}


def test_uninstall_leaves_a_foreign_destination_exactly_as_it_was(tmp_path: Path) -> None:
    """Force does not exist here at all, so a stranger's skill is reported and kept."""

    target = tmp_path / "target"
    before = foreign_skill(target, "galley")

    document = _run("uninstall", target, home=tmp_path / "home")
    entries = skill_entries(document)

    assert document["exit_code"] == COMPLETED
    assert entries["galley"]["action"] == "retained"
    assert entries["galley"]["state"] == "foreign"
    assert dispositions(entries["galley"]) == {"SKILL.md": "retained"}
    assert contents(target) == before


def test_uninstall_accepts_no_force_option(tmp_path: Path) -> None:
    """No option in this release authorises removing a file Galley cannot attribute to itself."""

    for result in run_public_cli(
        "skill",
        "uninstall",
        "--target",
        str(tmp_path / "target"),
        "--force",
        environment=isolated_home(tmp_path / "home"),
    ):
        assert result.returncode == 2
        assert result.stdout == ""


def test_uninstall_refuses_a_target_that_is_not_a_directory(tmp_path: Path) -> None:
    """A target Galley cannot read as a directory is refused rather than reported as empty."""

    target = tmp_path / "occupied"
    _ = target.write_text("not a directory\n", encoding="utf-8")

    document = _run("uninstall", target, home=tmp_path / "home")
    refusal = refusal_of(document)

    assert document["exit_code"] == REFUSED
    assert refusal["boundary"] == "skill-target-unusable"
    assert refusal["authority"] == "skill uninstall"
    assert target.read_text(encoding="utf-8") == "not a directory\n"


def test_uninstall_on_an_absent_target_reports_nothing_and_creates_nothing(tmp_path: Path) -> None:
    """Uninstall never creates the target it was asked to clean."""

    target = tmp_path / "never-existed"

    document = _run("uninstall", target, home=tmp_path / "home")

    assert document["exit_code"] == COMPLETED
    assert [entry["state"] for entry in skill_entries(document).values()] == ["absent", "absent"]
    assert not target.exists()
