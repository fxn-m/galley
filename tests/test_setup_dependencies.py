"""Hold first-run dependency bootstrap to the releases Galley's runtime actually uses."""

import re
from pathlib import Path

from galley.release_data import pinned_pandoc_version
from galley.tools.defuddle import PINNED_VERSION as DEFUDDLE_VERSION
from galley.tools.epubcheck import PINNED_VERSION as EPUBCHECK_VERSION
from galley.tools.resvg import PINNED_VERSION as RESVG_VERSION

SKILL = Path("src/galley/skills/galley-setup/SKILL.md")
DEPENDENCIES = SKILL.parent / "resources/dependencies.md"
README = Path("README.md")


def _dependency_requirements() -> dict[str, str]:
    """Read the release table the setup agent uses before it changes the machine."""

    return dict(
        re.findall(
            r"^\| `([a-z]+)` \| `([^`]+)` \| `\1 --version` \|",
            DEPENDENCIES.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
    )


def test_the_setup_skill_carries_the_runtime_dependency_pins() -> None:
    """Setup must install the releases the CLI actually records, from one bounded resource."""

    assert _dependency_requirements() == {
        "defuddle": DEFUDDLE_VERSION,
        "epubcheck": EPUBCHECK_VERSION,
        "pandoc": pinned_pandoc_version(),
        "resvg": RESVG_VERSION,
    }
    assert "[dependency bootstrap](resources/dependencies.md)" in SKILL.read_text(encoding="utf-8")


def test_setup_owns_dependency_installation_instead_of_assigning_it_to_the_user() -> None:
    """The quick start ends at the agent; platform installation is part of setup's work."""

    skill = SKILL.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")

    assert "Run the approved installation\ncommands yourself" in skill
    assert "not homework to hand back to them" in skill
    assert "Put the pinned command-line tools on your `PATH`" not in readme
    assert "your agent chooses the exact installation route for your machine" in readme
