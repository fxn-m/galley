"""Build isolated skill targets for the installed skill lifecycle commands.

Every test installs into its own directory under `tmp_path` and selects it with `--target`, which
is the reason that option exists: installation behaviour and discovery layout are exercised
without touching a real user profile. `HOME` is redirected as well, so the one test that exercises
the default target cannot reach the developer's own `.agents/skills`.
"""

import json
import subprocess
from pathlib import Path
from typing import cast

# The public name of the Galley-managed manifest. Hard-coded rather than imported: it is the file
# a user sees in their own skills directory, so a silent rename should fail these tests.
MANIFEST = ".galley-manifest.json"
SKILLS = ("galley", "galley-setup")
PACKAGED = Path("src/galley/skills")
STAGING_PREFIXES = (".galley-staged-", ".galley-replaced-")


def isolated_home(home: Path) -> dict[str, str]:
    """Select a throwaway home directory, so the default target is never the real one."""

    home.mkdir(parents=True, exist_ok=True)
    return {"HOME": str(home)}


def contents(root: Path) -> dict[str, bytes]:
    """Snapshot every file below one directory, so an untouched tree can be proven untouched."""

    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def stamps(root: Path) -> dict[str, int]:
    """Snapshot modification times, so a successful no-op can be proven to rewrite nothing."""

    return {
        str(path.relative_to(root)): path.stat().st_mtime_ns
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def packaged_files(skill: str) -> dict[str, bytes]:
    """Read one packaged skill tree from the repository, to compare an installation against."""

    root = PACKAGED / skill
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def manifest_of(target: Path, skill: str) -> dict[str, object]:
    """Read the manifest one installed skill directory carries."""

    document = cast(object, json.loads((target / skill / MANIFEST).read_text(encoding="utf-8")))
    assert isinstance(document, dict)
    return cast(dict[str, object], document)


def rewrite_manifest(target: Path, skill: str, document: dict[str, object]) -> None:
    """Replace one installed manifest, to stand in for an installation of an older Galley."""

    _ = (target / skill / MANIFEST).write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def foreign_skill(target: Path, skill: str) -> dict[str, bytes]:
    """Occupy one skill's destination with somebody else's skill, carrying no Galley manifest."""

    directory = target / skill
    directory.mkdir(parents=True)
    _ = (directory / "SKILL.md").write_text("---\nname: someone-else\n---\n", encoding="utf-8")
    return contents(target)


def skill_entries(document: dict[str, object]) -> dict[str, dict[str, object]]:
    """Index the per-skill facts by name, which is how every assertion here reads them."""

    skills = document["skills"]
    assert isinstance(skills, list)
    entries = [cast(dict[str, object], skill) for skill in cast(list[object], skills)]
    return {str(entry["name"]): entry for entry in entries}


def dispositions(entry: dict[str, object]) -> dict[str, str]:
    """Map each reported path to what the command did with it."""

    files = entry["files"]
    assert isinstance(files, list)
    reported = [cast(dict[str, object], file) for file in cast(list[object], files)]
    return {str(file["path"]): str(file["action"]) for file in reported}


def digests(entry: dict[str, object]) -> dict[str, str]:
    """Map each reported path to the hash the command reported for it."""

    files = entry["files"]
    assert isinstance(files, list)
    reported = [cast(dict[str, object], file) for file in cast(list[object], files)]
    return {str(file["path"]): str(file["sha256"]) for file in reported}


def differences(entry: dict[str, object]) -> list[str]:
    """Read the paths one skill entry says stop its destination matching its own manifest."""

    stated = entry["differences"]
    assert isinstance(stated, list)
    return sorted(str(path) for path in cast(list[object], stated))


def no_staging_left(target: Path) -> bool:
    """Prove no half-finished installation was left in the target, whatever the outcome."""

    if not target.exists():
        return True
    return not any(
        path.name.startswith(prefix) for path in target.iterdir() for prefix in STAGING_PREFIXES
    )


def document_of(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    """Read the versioned command document one invocation emitted on stdout."""

    document = cast(object, json.loads(result.stdout))
    assert isinstance(document, dict)
    return cast(dict[str, object], document)


def refusal_of(document: dict[str, object]) -> dict[str, object]:
    """Read the structured refusal one document carries, as a typed mapping."""

    refusal = document["refusal"]
    assert isinstance(refusal, dict)
    return cast(dict[str, object], refusal)


def refusal_fact(document: dict[str, object]) -> dict[str, object]:
    """Read the facts one refusal states, as a typed mapping."""

    fact = refusal_of(document)["fact"]
    assert isinstance(fact, dict)
    return cast(dict[str, object], fact)


def mapping_of(document: dict[str, object], key: str) -> dict[str, object]:
    """Read one object-valued field of a command document."""

    value = document[key]
    assert isinstance(value, dict)
    return cast(dict[str, object], value)
