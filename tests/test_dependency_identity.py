"""Observe dependency identity through CLI invocations and native command wrappers."""

import json
import os
import shlex
import shutil
import sys
from pathlib import Path

import pytest

from galley.cli import main
from tests.public_cli import prepare


def recording_command(
    root: Path, tool: str, *, version_response: str | None = None
) -> tuple[Path, Path]:
    """Record calls while preserving the real tool's arguments, output and exit status."""

    native = shutil.which(tool)
    assert native is not None
    command = root / tool
    log = root / f"{tool}.calls"
    response = (
        ""
        if version_response is None
        else f'if [ "$1" = --version ]; then printf "%s" {shlex.quote(version_response)}; '
        "exit 0; fi\n"
    )
    _ = command.write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$1" >> {shlex.quote(str(log))}\n'
        f"{response}"
        f'exec {shlex.quote(native)} "$@"\n',
        encoding="utf-8",
    )
    command.chmod(0o755)
    return command, log


def test_preparation_probes_each_tool_once_and_still_runs_every_native_operation(
    tmp_path: Path,
) -> None:
    pandoc, pandoc_log = recording_command(tmp_path, "pandoc")
    resvg, resvg_log = recording_command(tmp_path, "resvg")
    for name, colour in (("one", "red"), ("two", "blue")):
        _ = (tmp_path / f"{name}.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80">'
            f'<rect width="80" height="80" fill="{colour}"/></svg>',
            encoding="utf-8",
        )
    source = tmp_path / "source.md"
    _ = source.write_text("# Identity\n\n![One](one.svg)\n\n![Two](two.svg)\n", encoding="utf-8")
    result = prepare(
        tmp_path,
        source,
        environment={"GALLEY_PANDOC": str(pandoc), "GALLEY_RESVG": str(resvg)},
    )
    assert result.output.is_file()
    assert pandoc_log.read_text().splitlines() == [
        "--version",
        "--from",
        "--print-default-template=epub3",
        "--resource-path",
    ]
    assert resvg_log.read_text().splitlines() == [
        "--version",
        "--skip-system-fonts",
        "--skip-system-fonts",
        "--skip-system-fonts",
    ]
    assert result.report["galley"]["dependencies"]["pandoc"] == "3.10"
    assert result.report["galley"]["dependencies"]["resvg"] == "0.48.1"


@pytest.mark.parametrize("version", ["pandoc 2.0\n", ""])
def test_preparation_reuses_incompatible_and_unanswered_version_observations(
    tmp_path: Path, version: str
) -> None:
    pandoc, log = recording_command(tmp_path, "pandoc", version_response=version)
    source = tmp_path / "source.md"
    _ = source.write_text("# Identity\n\nOne paragraph.\n", encoding="utf-8")
    result = prepare(tmp_path, source, environment={"GALLEY_PANDOC": str(pandoc)})
    assert log.read_text().splitlines().count("--version") == 1
    expected = "2.0" if version else None
    assert result.report["source"]["parser"]["version"] == expected
    assert result.report["preparation"]["packaging"]["version"] == expected
    assert result.report["preparation"]["packaging"]["matches_pinned_version"] is False
    assert result.report["galley"]["dependencies"].get("pandoc") == expected


def test_repeated_cli_invocations_refresh_overrides_versions_and_missing_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Use the console entry function repeatedly in one process, including a refusal exit."""

    source = tmp_path / "source.md"
    _ = source.write_text("# Identity\n\nOne paragraph.\n", encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv", ["galley", "inspect", str(source), "--profile", "x4-crosspoint", "--json"]
    )
    selected = tmp_path / "pandoc"
    monkeypatch.setenv("GALLEY_PANDOC", str(selected))
    with pytest.raises(SystemExit) as refused:
        main()
    assert refused.value.code == 3
    report = json.loads(capsys.readouterr().out)
    assert report["refusal"]["fact"]["reason"] == "not-found"

    # The formerly absent command is installed, then replaced at the very same path.
    for version in ("3.10", "2.0"):
        _, log = recording_command(tmp_path, "pandoc", version_response=f"pandoc {version}\n")
        with pytest.raises(SystemExit) as completed:
            main()
        assert completed.value.code == 0
        report = json.loads(capsys.readouterr().out)
        assert report["galley"]["dependencies"]["pandoc"] == version
    assert log.read_text().splitlines() == ["--version", "--from", "--version", "--from"]

    monkeypatch.setenv("GALLEY_PANDOC", "galley-pandoc-now-missing")
    with pytest.raises(SystemExit) as changed:
        main()
    assert changed.value.code == 3
    report = json.loads(capsys.readouterr().out)
    assert report["refusal"]["fact"]["tool"] == "galley-pandoc-now-missing"
    assert "pandoc" not in report["galley"]["dependencies"]


def test_a_new_cli_invocation_resolves_the_same_command_against_its_new_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source.md"
    _ = source.write_text("# Identity\n\nOne paragraph.\n", encoding="utf-8")
    directories = [tmp_path / "first", tmp_path / "second"]
    for directory, version in zip(directories, ("3.10", "2.0"), strict=True):
        directory.mkdir()
        command, _ = recording_command(directory, "pandoc", version_response=f"pandoc {version}\n")
        _ = command.rename(directory / "selected-pandoc")
    original_path = os.environ.get("PATH", "")
    monkeypatch.setenv("GALLEY_PANDOC", "selected-pandoc")
    monkeypatch.setattr(
        sys, "argv", ["galley", "inspect", str(source), "--profile", "x4-crosspoint", "--json"]
    )
    for directory, version in zip(directories, ("3.10", "2.0"), strict=True):
        monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{original_path}")
        with pytest.raises(SystemExit) as completed:
            main()
        assert completed.value.code == 0
        report = json.loads(capsys.readouterr().out)
        assert report["galley"]["dependencies"]["pandoc"] == version
        assert report["source"]["parser"]["tool"] == "pandoc"
        assert (directory / "pandoc.calls").read_text().splitlines() == ["--version", "--from"]
