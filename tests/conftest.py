"""Answer EPUBCheck invocations instantly unless a test opts into the real tool.

Every prepare and audit run shells out to EPUBCheck, and each real invocation pays for a
JVM start before any checking begins. Almost no test is about EPUBCheck's own behaviour,
so by default the suite selects a stand-in that reports the pinned version and a clean
result immediately. The `real_epubcheck` marker restores the real command for the tests
whose claim depends on it: conformance retention, audit immutability, and the guarantee
that a prepared artifact truly conforms.
"""

from pathlib import Path

import pytest

# The same shape a real run writes: a checker block naming the pinned version, no
# messages, and an empty inventory. Argument three is the destination the caller names.
FAKE_EPUBCHECK = """#!/bin/sh
printf '{"checker":{"checkerVersion":"5.3.0","nFatal":0,"nError":0,"nWarning":0,"nUsage":0},\
"messages":[],"items":[],"publication":{}}' > "$3"
exit 0
"""


@pytest.fixture(scope="session")
def fake_epubcheck(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Write one instant EPUBCheck stand-in for the whole test session."""

    command = tmp_path_factory.mktemp("fake-epubcheck") / "epubcheck"
    _ = command.write_text(FAKE_EPUBCHECK, encoding="utf-8")
    command.chmod(0o755)
    return command


@pytest.fixture(autouse=True)
def fast_epubcheck(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, fake_epubcheck: Path
) -> None:
    """Select the stand-in through the environment every child process inherits.

    Tests that select their own command still win: an explicit `GALLEY_EPUBCHECK` in a
    test's environment overrides this inherited default.
    """

    if "real_epubcheck" in request.keywords:
        return
    monkeypatch.setenv("GALLEY_EPUBCHECK", str(fake_epubcheck))
