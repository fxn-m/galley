"""Compact adapter parity; detailed behaviour belongs to the installed-command journeys."""

import json
from pathlib import Path

import pytest

from tests.support.crosspoint_server import crosspoint
from tests.support.markdown_fixtures import PLAIN_BOOK, write_markdown
from tests.support.prepared_epub import PreparedEpub
from tests.support.public_cli import public_cli_commands, run_command
from tests.support.workspace_fixtures import valid_workspace, workspace_environment


@pytest.fixture(params=public_cli_commands(), ids=("galley", "python-module"))
def entry_point(request: pytest.FixtureRequest) -> list[str]:
    return list(request.param)


@pytest.mark.parametrize("json_output", (True, False), ids=("json", "human"))
def test_entry_points_prepare_a_default_cover_and_expose_the_same_document_commands(
    tmp_path: Path, entry_point: list[str], json_output: bool
) -> None:
    source = write_markdown(tmp_path / "source.md", PLAIN_BOOK)
    output = tmp_path / "book.epub"
    evidence = output.with_suffix(".galley")
    form = ("--json",) if json_output else ()
    common = ("--profile", "x4-crosspoint", *form)
    result = run_command(entry_point, "prepare", str(source), "--output", str(output), *common)
    assert (result.returncode, result.stderr) == (0, ""), result.stdout
    report = json.loads((evidence / "report.json").read_text())
    assert report["outcome"] == "completed"
    cover = next(
        item
        for item in report["preparation"]["images"]["records"]
        if item["origin"] == "default-cover"
    )
    assert cover["artifact"]["cover"] is True
    book = PreparedEpub(output)
    assert book.metadata("title") == ["A Plain Book"]
    if json_output:
        assert json.loads(result.stdout) == report
    else:
        assert 'Cover: Default Cover, "A Plain Book" by Ada Lovelace' in result.stdout
        assert f"Artifact: {output.resolve()}" in result.stdout

    for command, locator in (("inspect", source), ("audit", output)):
        result = run_command(entry_point, command, str(locator), *common)
        assert (result.returncode, result.stderr) == (0, ""), result.stdout
        if json_output:
            document = json.loads(result.stdout)
            assert document["outcome"] == "completed"
            assert document["galley"]["command"] == command
        else:
            assert f"{command}: completed" in result.stdout

    result = run_command(
        entry_point, "localise", str(source), "--evidence-dir", str(tmp_path / "localised"), *common
    )
    assert (result.returncode, result.stderr) == (3, ""), result.stdout
    if json_output:
        assert json.loads(result.stdout)["refusal"]["boundary"] == "no-remote-images"
    else:
        assert "localise: refused" in result.stdout
        assert "source references no remote image" in result.stdout


@pytest.mark.parametrize("json_output", (True, False), ids=("json", "human"))
def test_entry_points_preserve_structured_refusal_and_human_explanation(
    tmp_path: Path, entry_point: list[str], json_output: bool
) -> None:
    source = write_markdown(tmp_path / "source.md", PLAIN_BOOK)
    original = source.read_bytes()
    output = tmp_path / "refused.epub"
    form = ("--json",) if json_output else ()
    result = run_command(
        entry_point, "prepare", str(source), "--output", str(output), "--profile", "missing", *form
    )
    assert (result.returncode, result.stderr) == (3, "")
    assert source.read_bytes() == original
    assert not output.exists()
    if json_output:
        report = json.loads(result.stdout)
        assert report["galley"]["report_schema"] == "galley/report/1"
        assert report["refusal"]["boundary"] == "unknown-profile"
        assert report["refusal"]["artifact_written"] is False
    else:
        assert "prepare: refused" in result.stdout
        assert "unknown Device Profile: missing" in result.stdout


@pytest.mark.parametrize("json_output", (True, False), ids=("json", "human"))
def test_entry_points_validate_and_check_the_selected_workspace(
    tmp_path: Path, entry_point: list[str], json_output: bool
) -> None:
    workspace = tmp_path / "workspace"
    _ = valid_workspace(workspace)
    environment = workspace_environment(workspace, tmp_path / "home")
    form = ("--json",) if json_output else ()
    for family, action in (("config", "validate"), ("inbox", "check")):
        result = run_command(entry_point, family, action, *form, environment=environment)
        assert (result.returncode, result.stderr) == (0, ""), result.stdout
        if json_output:
            document = json.loads(result.stdout)
            assert document["outcome"] == "completed"
            assert document["galley"]["command"] == f"{family} {action}"
        else:
            assert f"{family} {action}: completed" in result.stdout


@pytest.mark.parametrize("json_output", (True, False), ids=("json", "human"))
def test_entry_points_install_and_uninstall_complete_skills(
    tmp_path: Path, entry_point: list[str], json_output: bool
) -> None:
    target = tmp_path / "skills"
    environment = workspace_environment(tmp_path / "workspace", tmp_path / "home")
    form = ("--json",) if json_output else ()
    for action in ("install", "uninstall"):
        result = run_command(
            entry_point, "skill", action, "--target", str(target), *form, environment=environment
        )
        assert (result.returncode, result.stderr) == (0, ""), result.stdout
        if json_output:
            document = json.loads(result.stdout)
            assert document["outcome"] == "completed"
            assert document["galley"]["command"] == f"skill {action}"
        else:
            assert f"skill {action}: completed" in result.stdout
        assert (target / "galley" / "SKILL.md").exists() is (action == "install")


@pytest.mark.parametrize("json_output", (True, False), ids=("json", "human"))
def test_entry_points_probe_plan_and_deliver_a_ready_artifact(
    tmp_path: Path, entry_point: list[str], json_output: bool
) -> None:
    workspace = tmp_path / "workspace"
    _ = valid_workspace(workspace)
    environment = workspace_environment(workspace, tmp_path / "home")
    source = write_markdown(workspace / "inbox" / "source.md", PLAIN_BOOK)
    ready = run_command(
        entry_point,
        "prepare",
        str(source),
        "--ready",
        "--profile",
        "x4-crosspoint",
        "--json",
        environment=environment,
    )
    assert (ready.returncode, ready.stderr) == (0, ""), ready.stdout
    artifact = Path(json.loads(ready.stdout)["artifact"]["path"])
    form = ("--json",) if json_output else ()
    with crosspoint() as (host, device):
        for command, expected in (
            (("device", "status"), "completed"),
            (("deliver", str(artifact), "--plan"), "planned"),
            (("deliver", str(artifact)), "delivered"),
        ):
            result = run_command(
                entry_point, *command, "--host", host, *form, environment=environment
            )
            assert (result.returncode, result.stderr) == (0, ""), result.stdout
            if json_output:
                assert json.loads(result.stdout)["outcome"] == expected
            else:
                assert f": {expected}" in result.stdout
            assert device.upload_requests == (1 if expected == "delivered" else 0)
        assert device.files == {artifact.name: artifact.stat().st_size}
