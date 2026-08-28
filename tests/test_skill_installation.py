"""Install both Agent Skills through the installed public CLI, or refuse without writing.

Installation is the one thing Galley does inside a directory it does not own, so almost every
assertion here is about what stayed the same: a refusal leaves the target byte-for-byte as it was,
force reaches only the two named skill directories, and a successful no-op rewrites nothing.
"""

from pathlib import Path

from tests.public_cli import public_cli_commands, run_command, run_public_cli
from tests.skill_fixtures import (
    MANIFEST,
    SKILLS,
    contents,
    digests,
    dispositions,
    document_of,
    foreign_skill,
    isolated_home,
    manifest_of,
    mapping_of,
    no_staging_left,
    packaged_files,
    rewrite_manifest,
    skill_entries,
    stamps,
)

COMPLETED = 0


def _install(target: Path | None, *arguments: str, home: Path) -> list[dict[str, object]]:
    """Install through each public entry point into one target, returning both documents.

    Both entry points run against the same target, so the second one is a repeat of the first.
    Assertions read `[0]` — the run that met the state the test set up — and the repeat is itself
    worth having, since a command whose second run disagreed with its first would be caught here.
    """

    selection = () if target is None else ("--target", str(target))
    documents: list[dict[str, object]] = []
    for result in run_public_cli(
        "skill", "install", *selection, *arguments, "--json", environment=isolated_home(home)
    ):
        documents.append(document_of(result))
        documents[-1]["exit_code"] = result.returncode
    return documents


def test_a_missing_target_installs_both_skills_and_records_every_hash(tmp_path: Path) -> None:
    """The first install writes both complete trees plus the manifest that speaks for them."""

    for entry_point, command in enumerate(public_cli_commands("skill", "install")):
        target = tmp_path / f"target-{entry_point}"
        result = run_command(
            command,
            "--target",
            str(target),
            "--json",
            environment=isolated_home(tmp_path / "home"),
        )
        document = document_of(result)
        entries = skill_entries(document)
        source = mapping_of(document, "source")

        assert result.returncode == COMPLETED
        assert document["outcome"] == "completed"
        assert [entry["action"] for entry in entries.values()] == ["installed", "installed"]
        for skill in SKILLS:
            packaged = packaged_files(skill)
            installed = contents(target / skill)
            manifest = manifest_of(target, skill)
            assert {path: data for path, data in installed.items() if path != MANIFEST} == packaged
            assert manifest["schema"] == "galley/skill-manifest/1"
            assert manifest["galley_version"] == source["galley_version"]
            assert set(digests(entries[skill])) == set(packaged)
            assert set(dispositions(entries[skill]).values()) == {"written"}
        assert no_staging_left(target)


def test_the_default_target_is_the_standard_user_skills_location(tmp_path: Path) -> None:
    """No option means the standard user `.agents/skills` directory, and nothing else."""

    home = tmp_path / "home"
    document = _install(None, home=home)[0]
    target = home / ".agents" / "skills"

    assert document["exit_code"] == COMPLETED
    assert document["target"] == {"source": "default", "path": str(target.resolve())}
    assert sorted(path.name for path in target.iterdir()) == sorted(SKILLS)


def test_an_identical_managed_installation_is_a_successful_no_op(tmp_path: Path) -> None:
    """A second install of the same version writes nothing at all, and says so."""

    target = tmp_path / "target"
    home = tmp_path / "home"
    _ = _install(target, home=home)[0]
    before = stamps(target)

    document = _install(target, home=home)[0]
    entries = skill_entries(document)

    assert document["exit_code"] == COMPLETED
    assert [entry["action"] for entry in entries.values()] == ["unchanged", "unchanged"]
    assert set(dispositions(entries["galley"]).values()) == {"unchanged"}
    assert stamps(target) == before


def test_an_older_intact_managed_installation_upgrades_to_the_packaged_version(
    tmp_path: Path,
) -> None:
    """An installation that matches its own older manifest is replaced by the packaged one."""

    target = tmp_path / "target"
    home = tmp_path / "home"
    _ = _install(target, home=home)[0]
    older = manifest_of(target, "galley")
    installed_version = older["galley_version"]
    rewrite_manifest(target, "galley", {**older, "galley_version": "0.0.9"})

    document = _install(target, home=home)[0]
    entries = skill_entries(document)

    assert document["exit_code"] == COMPLETED
    assert entries["galley"]["action"] == "upgraded"
    assert entries["galley"]["state"] == "managed"
    assert entries["galley"]["manifest"] == {
        "galley_version": "0.0.9",
        "files": len(packaged_files("galley")),
    }
    assert manifest_of(target, "galley")["galley_version"] == installed_version
    installed = contents(target / "galley")
    assert {path: data for path, data in installed.items() if path != MANIFEST} == packaged_files(
        "galley"
    )


def test_force_replaces_only_the_two_named_skill_directories(tmp_path: Path) -> None:
    """Force is permission to overwrite Galley's own surface, not to tidy the target."""

    target = tmp_path / "target"
    _ = foreign_skill(target, "galley")
    _ = foreign_skill(target, "galley-setup")
    (target / "other-product").mkdir()
    _ = (target / "other-product" / "SKILL.md").write_text("theirs\n", encoding="utf-8")
    _ = (target / "notes.txt").write_text("loose\n", encoding="utf-8")
    unrelated = {
        path: data
        for path, data in contents(target).items()
        if not path.startswith(("galley/", "galley-setup/"))
    }

    document = _install(target, "--force", home=tmp_path / "home")[0]
    entries = skill_entries(document)

    assert document["exit_code"] == COMPLETED
    assert [entry["action"] for entry in entries.values()] == ["replaced", "replaced"]
    for skill in SKILLS:
        placed = contents(target / skill)
        assert {path: data for path, data in placed.items() if path != MANIFEST} == packaged_files(
            skill
        )
    assert {
        path: data
        for path, data in contents(target).items()
        if not path.startswith(("galley/", "galley-setup/"))
    } == unrelated


def test_the_human_rendering_states_the_same_source_target_and_actions(tmp_path: Path) -> None:
    """Concise output is a second rendering of the document, never a second account of it."""

    target = tmp_path / "target"
    for result in run_public_cli(
        "skill", "install", "--target", str(target), environment=isolated_home(tmp_path / "home")
    ):
        assert result.returncode == COMPLETED
        assert "skill install: completed" in result.stdout
        assert str(target.resolve()) in result.stdout
        for skill in SKILLS:
            assert f"{skill}: " in result.stdout
