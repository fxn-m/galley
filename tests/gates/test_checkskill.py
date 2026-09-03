from pathlib import Path

from scripts.checkskill import (
    REQUIRED_SKILLS,
    SKILL_ROOT,
    validate_packaged_manifests,
    validate_skills,
)


def write_skill(root: Path, *, description: str, body: str = "# Example\n") -> Path:
    skill = root / "example"
    skill.mkdir(parents=True)
    _ = (skill / "SKILL.md").write_text(
        f"---\nname: example\ndescription: {description}\n---\n\n{body}",
        encoding="utf-8",
    )
    return skill


def test_committed_skill_tree_is_valid() -> None:
    assert validate_skills(Path(SKILL_ROOT)) == []


def test_skill_description_is_limited_to_fifty_words(tmp_path: Path) -> None:
    _ = write_skill(tmp_path, description=" ".join(["word"] * 51))

    assert validate_skills(tmp_path, required=("example",)) == [
        "example/SKILL.md: description has 51 words; maximum is 50"
    ]


def test_skill_prohibition_budget_is_enforced(tmp_path: Path) -> None:
    body = "\n".join(["Do not guess."] * 6)
    _ = write_skill(tmp_path, description="A valid trigger description.", body=body)

    assert validate_skills(tmp_path, required=("example",)) == [
        "example/SKILL.md: body has 6 prohibition phrases; maximum is 5"
    ]


def test_linked_skill_resources_must_exist(tmp_path: Path) -> None:
    _ = write_skill(
        tmp_path,
        description="A valid trigger description.",
        body="Read [the guide](resources/guide.md).\n",
    )

    assert validate_skills(tmp_path, required=("example",)) == [
        "example/SKILL.md: linked resource does not exist: resources/guide.md"
    ]


def test_the_skill_root_must_hold_exactly_the_skills_this_release_ships(tmp_path: Path) -> None:
    """Both Agent Skills are product surfaces the CLI installs by name, so the set is fixed."""

    _ = write_skill(tmp_path, description="A valid trigger description.")

    assert validate_skills(tmp_path) == [
        *(f"{tmp_path}/{name}: required skill is missing" for name in sorted(REQUIRED_SKILLS)),
        f"{tmp_path}/example: unexpected skill directory",
    ]


def test_the_packaged_manifest_gate_accounts_for_every_packaged_skill_file() -> None:
    """The manifest is built rather than shipped, so the builder is what has to be gated."""

    assert validate_packaged_manifests(Path(SKILL_ROOT)) == []


def test_the_packaged_manifest_gate_refuses_a_tree_it_did_not_read(tmp_path: Path) -> None:
    """A gate silently validating a different tree than the installer reads proves nothing."""

    errors = validate_packaged_manifests(tmp_path)

    assert len(errors) == 1
    assert "the packaged skills are read from" in errors[0]
