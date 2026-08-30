import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

from tests.epub_fixtures import write_epub
from tests.markdown_fixtures import RETAINED_EVIDENCE_BASELINE, native_ast, write_markdown
from tests.skill_fixtures import (
    MANIFEST,
    SKILLS,
    contents,
    document_of,
    mapping_of,
    packaged_files,
    skill_entries,
)

ROOT = Path(__file__).resolve().parent.parent


def run(command: list[str], *, cwd: Path, environment: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_built_distribution_exposes_profiles_and_reports(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    assert uv is not None
    distribution_dir = tmp_path / "dist"
    environment_dir = tmp_path / "environment"
    _ = run([uv, "build", "--out-dir", str(distribution_dir), str(ROOT)], cwd=tmp_path)

    wheels = list(distribution_dir.glob("*.whl"))
    assert len(wheels) == 1
    assert len(list(distribution_dir.glob("*.tar.gz"))) == 1
    _ = run([uv, "venv", "--python", sys.executable, str(environment_dir)], cwd=tmp_path)
    executable_dir = "Scripts" if os.name == "nt" else "bin"
    suffix = ".exe" if os.name == "nt" else ""
    python = environment_dir / executable_dir / f"python{suffix}"
    _ = run([uv, "pip", "install", "--python", str(python), str(wheels[0])], cwd=tmp_path)

    clean_environment = os.environ.copy()
    clean_environment.pop("PYTHONPATH", None)
    clean_environment["PYTHONNOUSERSITE"] = "1"
    galley = environment_dir / executable_dir / f"galley{suffix}"
    output = run(
        [str(galley), "profiles", "show", "x4-crosspoint", "--json"],
        cwd=tmp_path,
        environment=clean_environment,
    )

    profile = json.loads(output)
    assert profile["schema"] == "galley/device-profile/2"
    assert profile["id"] == "x4-crosspoint"
    assert profile["profile_version"] == "0.4.0"
    assert "parts" not in profile

    source = tmp_path / "unread.md"
    original = b"The installed refusal must not read or mutate this source.\n"
    _ = source.write_bytes(original)
    refused = subprocess.run(
        [str(galley), "inspect", str(source), "--profile", "missing", "--json"],
        cwd=tmp_path,
        env=clean_environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert (refused.returncode, refused.stderr) == (3, "")
    report = json.loads(refused.stdout)
    assert report["galley"]["report_schema"] == "galley/report/1"
    assert report["outcome"] == "refused"
    assert report["refusal"]["boundary"] == "unknown-profile"
    assert source.read_bytes() == original

    inspected = write_markdown(tmp_path / "installed.md")
    evidence = tmp_path / "installed-evidence"
    output = run(
        [
            str(galley),
            "inspect",
            str(inspected),
            "--profile",
            "x4-crosspoint",
            "--json",
            "--evidence-dir",
            str(evidence),
        ],
        cwd=tmp_path,
        environment=clean_environment,
    )

    report = json.loads(output)
    assert report["outcome"] == "completed"
    assert report["canonical_document"]["schema"] == "galley/canonical-document/1"
    assert report["galley"]["dependencies"]["pandoc"] == "3.10"
    document = json.loads((evidence / "canonical-document.json").read_text(encoding="utf-8"))
    assert document["pandoc"] == native_ast(inspected)
    assert (evidence / "preservation-baseline.txt").read_text(encoding="utf-8") == (
        RETAINED_EVIDENCE_BASELINE
    )

    book = write_epub(tmp_path / "installed.epub")
    before = book.read_bytes()
    audited = run(
        [str(galley), "audit", str(book), "--profile", "x4-crosspoint", "--json"],
        cwd=tmp_path,
        environment=clean_environment,
    )

    report = json.loads(audited)
    artifact = report["artifact"]
    assert artifact["package"]["path"] == "EPUB/package.opf"
    assert artifact["problems"] == []
    assert artifact["conformance"]["version"] == "5.3.0"
    assert artifact["conformance"]["valid"] is True
    assert artifact["conformance"]["non_requirements"][0]["id"] == "package-validity"
    assert report["galley"]["dependencies"]["epubcheck"] == "5.3.0"
    assert book.read_bytes() == before


def test_source_and_wheel_discover_the_same_complete_profile_set(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    assert uv is not None
    project = tmp_path / "project"
    _ = shutil.copytree(ROOT / "src", project / "src")
    _ = shutil.copytree(ROOT / "profiles", project / "profiles")
    for name in ("LICENSE", "README.md", "pyproject.toml"):
        _ = shutil.copy2(ROOT / name, project / name)

    second = project / "profiles" / "synthetic-crosspoint"
    _ = shutil.copytree(project / "profiles" / "x4-crosspoint", second)
    manifest = second / "profile.yaml"
    text = manifest.read_text(encoding="utf-8")
    text = text.replace("id: x4-crosspoint", "id: synthetic-crosspoint", 1)
    text = text.replace("profile_version: 0.4.0", "profile_version: 1.0.0", 1)
    _ = manifest.write_text(text, encoding="utf-8")

    source_environment = os.environ.copy()
    source_environment["PYTHONPATH"] = str(project / "src")
    source_environment["PYTHONNOUSERSITE"] = "1"
    source_output = run(
        [sys.executable, "-m", "galley", "profiles", "list", "--json"],
        cwd=project,
        environment=source_environment,
    )

    distribution_dir = tmp_path / "dist"
    environment_dir = tmp_path / "environment"
    _ = run([uv, "build", "--out-dir", str(distribution_dir), str(project)], cwd=tmp_path)
    wheel = next(iter(distribution_dir.glob("*.whl")))
    _ = run([uv, "venv", "--python", sys.executable, str(environment_dir)], cwd=tmp_path)
    executable_dir = "Scripts" if os.name == "nt" else "bin"
    suffix = ".exe" if os.name == "nt" else ""
    python = environment_dir / executable_dir / f"python{suffix}"
    _ = run([uv, "pip", "install", "--python", str(python), str(wheel)], cwd=tmp_path)
    wheel_environment = os.environ.copy()
    wheel_environment.pop("PYTHONPATH", None)
    wheel_environment["PYTHONNOUSERSITE"] = "1"
    galley = environment_dir / executable_dir / f"galley{suffix}"
    wheel_output = run(
        [str(galley), "profiles", "list", "--json"],
        cwd=tmp_path,
        environment=wheel_environment,
    )

    source_profiles = json.loads(source_output)
    wheel_profiles = json.loads(wheel_output)
    assert source_profiles == wheel_profiles
    assert [(profile["id"], profile["profile_version"]) for profile in source_profiles] == [
        ("kindle-ios-personal-documents", "0.3.0"),
        ("synthetic-crosspoint", "1.0.0"),
        ("x4-crosspoint", "0.4.0"),
    ]


def _distribution_names(archive: Path) -> set[str]:
    """List a built distribution's own entries, whichever kind of archive it is."""

    if archive.suffix == ".whl":
        return set(zipfile.ZipFile(archive).namelist())
    with tarfile.open(archive) as bundle:
        return set(bundle.getnames())


def test_both_distributions_carry_complete_skills_and_cover_font(tmp_path: Path) -> None:
    """Runtime cover rendering and skill installation must not depend on the checkout."""

    uv = shutil.which("uv")
    assert uv is not None
    distribution_dir = tmp_path / "dist"
    _ = run([uv, "build", "--out-dir", str(distribution_dir), str(ROOT)], cwd=tmp_path)

    wheel = _distribution_names(next(iter(distribution_dir.glob("*.whl"))))
    sdist = _distribution_names(next(iter(distribution_dir.glob("*.tar.gz"))))
    for skill in SKILLS:
        for relative in packaged_files(skill):
            assert f"galley/skills/{skill}/{relative}" in wheel
            assert f"galley-0.1.9/src/galley/skills/{skill}/{relative}" in sdist
    for asset in (
        "AtkinsonHyperlegible-Regular.otf",
        "AtkinsonHyperlegible-OFL.txt",
    ):
        assert f"galley/assets/fonts/{asset}" in wheel
        assert f"galley-0.1.9/src/galley/assets/fonts/{asset}" in sdist


def test_the_installed_cli_installs_skills_from_the_distribution_not_the_checkout(
    tmp_path: Path,
) -> None:
    """The whole point of shipping the skills is that the source tree is never consulted."""

    uv = shutil.which("uv")
    assert uv is not None
    distribution_dir = tmp_path / "dist"
    environment_dir = tmp_path / "environment"
    _ = run([uv, "build", "--out-dir", str(distribution_dir), str(ROOT)], cwd=tmp_path)
    wheel = next(iter(distribution_dir.glob("*.whl")))
    _ = run([uv, "venv", "--python", sys.executable, str(environment_dir)], cwd=tmp_path)
    executable_dir = "Scripts" if os.name == "nt" else "bin"
    suffix = ".exe" if os.name == "nt" else ""
    python = environment_dir / executable_dir / f"python{suffix}"
    _ = run([uv, "pip", "install", "--python", str(python), str(wheel)], cwd=tmp_path)

    clean_environment = os.environ.copy()
    clean_environment.pop("PYTHONPATH", None)
    clean_environment["PYTHONNOUSERSITE"] = "1"
    clean_environment["HOME"] = str(tmp_path / "home")
    galley = environment_dir / executable_dir / f"galley{suffix}"
    target = tmp_path / "agents" / "skills"
    installed = subprocess.run(
        [str(galley), "skill", "install", "--target", str(target), "--json"],
        cwd=tmp_path,
        env=clean_environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert (installed.returncode, installed.stderr) == (0, "")
    document = document_of(installed)
    source = mapping_of(document, "source")
    envelope = mapping_of(document, "galley")
    read_from = Path(str(source["path"]))

    assert envelope["command"] == "skill install"
    assert envelope["document_schema"] == "galley/skill-installation/1"
    assert environment_dir in read_from.parents
    assert ROOT not in read_from.parents and read_from != ROOT / "src/galley/skills"
    entries = skill_entries(document)
    for skill in SKILLS:
        assert entries[skill]["action"] == "installed"
        placed = contents(target / skill)
        assert {path: data for path, data in placed.items() if path != MANIFEST} == packaged_files(
            skill
        )

    removed = subprocess.run(
        [str(galley), "skill", "uninstall", "--target", str(target), "--json"],
        cwd=tmp_path,
        env=clean_environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert (removed.returncode, removed.stderr) == (0, "")
    assert contents(target) == {}
