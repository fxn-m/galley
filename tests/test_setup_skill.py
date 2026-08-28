"""Hold the Setup Skill to the CLI it teaches and the configuration it authors.

The skill is the only author of Workspace Configuration, which makes its annotated template and
decision set product surface rather than documentation: a template the validator refuses would be
a first-run conversation that ends in a refusal, and a boundary it tells an agent to read would be
advice about a string Galley never emits.
"""

import re
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.public_cli import public_cli_commands, run_command, run_public_cli
from tests.workspace_fixtures import (
    command_document,
    entries,
    field,
    inbox_table,
    isolated_home,
    tree,
    valid_workspace,
    write_configuration,
)

SKILL = Path("src/galley/skills/galley-setup")
CONFIGURATION = SKILL / "resources/workspace-config.md"
MAIN_SKILL = Path("src/galley/skills/galley/SKILL.md")
# The six persisted configuration decisions setup may need from the user, in their supported
# order. Reader scope controls which apply but is deliberately not a configuration key.
REQUIRED_SUBJECTS = ("workspace", "inboxes", "recursion", "host", "destination", "probe")
COMMAND_GROUPS = (("config", "validate"), ("device", "status"))
OWNED_DIRECTORIES = ("work", "ready", "ready/evidence", "delivery")
UNUSED_LOOPBACK_PORT = "127.0.0.1:9"
COMPLETED = 0
REFUSED = 3


def _skill_text() -> str:
    return (SKILL / "SKILL.md").read_text(encoding="utf-8")


def _subjects() -> list[str]:
    """Read the question table's subject column, which is the whole question set."""

    return re.findall(r"^\| `([a-z]+)` \|", _skill_text(), flags=re.MULTILINE)


def _template() -> str:
    """Read the one annotated Workspace Configuration the skill ships as its template."""

    match = re.search(r"```toml\n(.*?)```", CONFIGURATION.read_text(encoding="utf-8"), re.DOTALL)
    assert match is not None, "the configuration contract ships no template"
    return match.group(1)


def _documented_boundaries(path: Path) -> set[str]:
    return set(re.findall(r"`([a-z]+(?:-[a-z]+)+)`", path.read_text(encoding="utf-8")))


def _templated_workspace(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """Build exactly the tree the skill says setup creates, configured by its own template."""

    home = tmp_path / "home"
    workspace = tmp_path / "Galley"
    (home / "Documents" / "Reading").mkdir(parents=True)
    (workspace / "inbox").mkdir(parents=True)
    for role in OWNED_DIRECTORIES:
        (workspace / role).mkdir(parents=True, exist_ok=True)
    _ = write_configuration(workspace, _template())
    return workspace, isolated_home(home)


def _help(*arguments: str) -> str:
    result = run_command(
        public_cli_commands(*arguments)[0], "--help", environment={"TERM": "dumb", "COLUMNS": "400"}
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_the_decision_set_is_exactly_the_six_subjects_the_specification_permits() -> None:
    """An extra decision would offer a choice that Galley does not support."""

    assert _subjects() == list(REQUIRED_SUBJECTS)


def test_reader_scope_is_not_a_seventh_configuration_key_or_profile_default() -> None:
    """Setup may tailor its questions to the readers in use without persisting a profile choice."""

    skill = " ".join(_skill_text().split())
    assert "Reader scope is onboarding context, not another configuration key" in skill
    assert "not a default profile" in skill
    assert "final three apply only when setup includes X4" in skill


def test_every_decision_has_a_default_for_the_one_response_fast_path() -> None:
    """The fast path is meaningful only when every configuration decision has a stated default."""

    rows = re.findall(r"^\| `([a-z]+)` \| ([^|]+)\| ([^|]+)\|$", _skill_text(), flags=re.MULTILINE)
    assert [subject for subject, _ask, _default in rows] == list(REQUIRED_SUBJECTS)
    for subject, ask, default in rows:
        assert "?" in ask, subject
        assert default.strip(), subject


def test_the_annotated_template_validates_through_the_read_only_validator(tmp_path: Path) -> None:
    """The template is what setup writes, so the validator it finishes by invoking must accept it."""

    workspace, environment = _templated_workspace(tmp_path)
    for result in run_public_cli(
        "config", "validate", "--workspace", str(workspace), "--json", environment=environment
    ):
        document = command_document(result)
        inboxes = entries(document, "inboxes")
        assert result.returncode == COMPLETED
        assert [inbox["name"] for inbox in inboxes] == ["inbox", "reading"]
        assert [inbox["path_resolution"] for inbox in inboxes] == ["relative", "home-relative"]
        assert [inbox["recursive"] for inbox in inboxes] == [False, True]
        assert {location["state"] for location in entries(document, "locations")} == {"usable"}
        connection = field(document, "connection")
        assert connection["destination"] == {"value": "/Books", "source": "configured"}


def test_the_owned_locations_setup_creates_are_the_roles_the_validator_reports(
    tmp_path: Path,
) -> None:
    """The skill creates what the CLI never will, so the two lists of roles have to agree."""

    workspace, environment = _templated_workspace(tmp_path)
    for result in run_public_cli(
        "config", "validate", "--workspace", str(workspace), "--json", environment=environment
    ):
        roles = [location["role"] for location in entries(command_document(result), "locations")]
        assert roles == ["work", "ready", "delivery"]
        for role in roles:
            assert f"`{role}/`" in _skill_text()


def test_the_default_workspace_the_skill_states_is_the_one_the_cli_resolves(tmp_path: Path) -> None:
    """The default is offered as an answer, so it is measured against resolution, not restated."""

    home = tmp_path / "home"
    assert "`~/Documents/Galley`" in _skill_text()
    for result in run_public_cli("config", "validate", "--json", environment=isolated_home(home)):
        workspace = field(command_document(result), "workspace")
        assert workspace["path"] == str((home / "Documents" / "Galley").resolve())


def test_every_option_the_setup_skill_names_exists_on_the_installed_cli() -> None:
    available = set[str]().union(
        *(set(re.findall(r"--[a-z-]+", _help(*group))) for group in COMMAND_GROUPS)
    )
    documented = set[str]()
    for path in sorted(SKILL.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for invocation in re.findall(r"`(galley [^`\n]+)`", text):
            documented.update(re.findall(r"--[a-z][a-z-]+", invocation))
        for block in re.findall(r"```\n(.*?)```", text, flags=re.DOTALL):
            if block.startswith("galley "):
                documented.update(re.findall(r"--[a-z][a-z-]+", block))

    assert documented, "the setup skill documents no options at all"
    assert documented <= available, sorted(documented - available)


def test_every_command_the_setup_skill_names_is_one_the_cli_exposes() -> None:
    named = set[str]()
    for path in sorted(SKILL.rglob("*.md")):
        named.update(re.findall(r"galley ([a-z]+ [a-z]+)", path.read_text(encoding="utf-8")))

    assert named == {" ".join(group) for group in COMMAND_GROUPS}
    for name in sorted(named):
        assert _help(*name.split())


def test_an_unreachable_device_probe_writes_nothing_and_leaves_setup_valid(tmp_path: Path) -> None:
    """Question 6 is optional and read-only, so its failure is a device fact and nothing more."""

    workspace, environment = _templated_workspace(tmp_path)
    before = tree(workspace)
    for result in run_public_cli(
        "device",
        "status",
        "--workspace",
        str(workspace),
        "--host",
        UNUSED_LOOPBACK_PORT,
        "--timeout",
        "0.2",
        "--json",
        environment=environment,
    ):
        assert result.returncode == REFUSED
        assert field(command_document(result), "refusal")["boundary"] == "device-unavailable"
    assert tree(workspace) == before
    for result in run_public_cli(
        "config", "validate", "--workspace", str(workspace), "--json", environment=environment
    ):
        assert result.returncode == COMPLETED
    assert tree(workspace) == before


def _missing_configuration(workspace: Path) -> None:
    workspace.mkdir(parents=True)


def _unreadable_configuration(workspace: Path) -> None:
    _ = valid_workspace(workspace)
    workspace.joinpath("galley.toml").chmod(0o000)


def _invalid_toml(workspace: Path) -> None:
    _ = write_configuration(workspace, "version = [\n")


def _unknown_key(workspace: Path) -> None:
    _ = write_configuration(
        workspace, 'version = 1\ncolour = "blue"\n\n' + inbox_table("inbox", "inbox")
    )


def _unsupported_version(workspace: Path) -> None:
    _ = write_configuration(workspace, "version = 2\n\n" + inbox_table("inbox", "inbox"))


def _duplicate_name(workspace: Path) -> None:
    _ = write_configuration(
        workspace,
        "version = 1\n\n" + inbox_table("inbox", "inbox") + inbox_table("inbox", "."),
    )


def _absent_inbox(workspace: Path) -> None:
    _ = write_configuration(workspace, "version = 1\n\n" + inbox_table("inbox", "missing"))


def _occupied_ready(workspace: Path) -> None:
    _ = valid_workspace(workspace, owned=False)
    _ = (workspace / "ready").write_text("occupied\n", encoding="utf-8")


CONFIGURATION_CASES: tuple[tuple[str, Callable[[Path], None]], ...] = (
    ("workspace-configuration-missing", _missing_configuration),
    ("unreadable-workspace-configuration", _unreadable_configuration),
    ("invalid-workspace-configuration", _invalid_toml),
    ("unknown-configuration-key", _unknown_key),
    ("unsupported-configuration-version", _unsupported_version),
    ("duplicate-inbox-name", _duplicate_name),
    ("inbox-unavailable", _absent_inbox),
    ("workspace-location-unusable", _occupied_ready),
)


@pytest.mark.parametrize(("boundary", "build"), CONFIGURATION_CASES)
def test_each_boundary_the_skill_names_is_one_the_validator_really_emits(
    tmp_path: Path, boundary: str, build: Callable[[Path], None]
) -> None:
    """The boundary table is what an agent reads to correct a file, so each entry is produced."""

    workspace = tmp_path / "Galley"
    build(workspace)
    configuration = workspace / "galley.toml"
    environment = isolated_home(tmp_path / "home")
    try:
        results = run_public_cli(
            "config", "validate", "--workspace", str(workspace), "--json", environment=environment
        )
    finally:
        if configuration.exists():
            configuration.chmod(0o600)
    for result in results:
        assert result.returncode == REFUSED
        assert field(command_document(result), "refusal")["boundary"] == boundary
    assert f"`{boundary}`" in CONFIGURATION.read_text(encoding="utf-8")


def test_the_main_skill_directs_to_this_skill_by_name_for_every_boundary_it_names() -> None:
    """The redirect is only useful if both surfaces name the same boundaries and the same skill."""

    main = MAIN_SKILL.read_text(encoding="utf-8")
    documented = _documented_boundaries(CONFIGURATION)
    named = {
        boundary
        for boundary in _documented_boundaries(MAIN_SKILL)
        if boundary in documented or boundary.endswith("configuration")
    }

    assert "galley-setup" in main
    assert "dependency-unavailable" in main
    assert named, "the main skill names no configuration boundary at all"
    assert named <= documented, sorted(named - documented)
