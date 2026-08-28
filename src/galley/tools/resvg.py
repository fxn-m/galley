"""Rasterise SVG through pinned resvg, with the font set stated rather than inherited.

Galley uses resvg because its renderer is not selected by the machine it runs on: it links no
system libraries, and `--skip-system-fonts` with an explicit font directory makes the font set an
input. Both flags are passed on every invocation, and a test enforces that call-site obligation.

Galley now ships one pinned, OFL-licensed face for agent-authored Cover Artwork. Its bytes are
copied into the otherwise isolated directory and their identity is reported. A missing or changed
font refuses rasterisation rather than silently changing typography. Renderer warnings are still
kept: an SVG asking for another face must not look deterministic merely because fallback drew it.
"""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal

from galley.tools.dependencies import diagnostic, run_dependency, selected_command

COMMAND_VARIABLE = "GALLEY_RESVG"
DEFAULT_COMMAND = "resvg"
PINNED_VERSION = "0.48.1"
FONTS = "fonts"
FONT_DIRECTORY = Path(__file__).resolve().parents[1] / "assets" / "fonts"
FONT_FILE = "AtkinsonHyperlegible-Regular.otf"
FONT_SHA256 = "4a0397a3709c5fc99e38d05469dcfbf1b3481196e89a01b7377f3163b188258e"
FONT_LICENSE_FILE = "AtkinsonHyperlegible-OFL.txt"
FONT_LICENSE_SHA256 = "64b9cae8727cb41ea9e8843103e69647c82383f3a902e2bb39b2c5d92083b6e1"
FONT_SOURCE_COMMIT = "1cb311624b2ddf88e9e37873999d165a8cd28b46"

UnavailableReason = Literal[
    "not-found",
    "not-executable",
    "timeout",
    "failed",
    "no-output",
    "font-unavailable",
]


@dataclass(frozen=True)
class Rendering:
    """One rasterisation attempt: the PNG bytes it produced, and what the renderer said."""

    data: bytes | None
    version: str | None
    messages: tuple[str, ...] = ()
    fonts: tuple[dict[str, object], ...] = ()
    reason: UnavailableReason | None = None
    detail: str = ""

    @property
    def facts(self) -> dict[str, object]:
        """Name the exact renderer, version and font policy that rasterised this image."""

        return {
            "detail": self.detail,
            "fonts": [dict(font) for font in self.fonts],
            "matches_pinned_version": self.version == PINNED_VERSION,
            "messages": list(self.messages),
            "pinned_version": PINNED_VERSION,
            "reason": self.reason,
            "system_fonts": False,
            "tool": DEFAULT_COMMAND,
            "version": self.version,
        }


def rasterise(data: bytes, workspace: Path) -> Rendering:
    """Render one SVG to PNG bytes, loading only fonts from the directory Galley states."""

    command = selected_command(COMMAND_VARIABLE, DEFAULT_COMMAND)
    version = installed_version(command)
    fonts = workspace / FONTS
    font_facts, font_error = _install_fonts(fonts)
    if font_error is not None:
        return Rendering(
            None,
            version,
            fonts=font_facts,
            reason="font-unavailable",
            detail=font_error,
        )
    source = workspace / "render.svg"
    destination = workspace / "render.png"
    _ = source.write_bytes(data)
    execution = run_dependency(
        command,
        ["--skip-system-fonts", "--use-fonts-dir", str(fonts), str(source), str(destination)],
    )
    completed = execution.completed
    if completed is None:
        return Rendering(
            None,
            version,
            fonts=font_facts,
            reason=execution.reason,
            detail=execution.detail,
        )
    messages = tuple(line.strip() for line in completed.stderr.splitlines() if line.strip())
    if completed.returncode != 0:
        detail = diagnostic(completed.stderr) or f"resvg exited {completed.returncode}"
        return Rendering(None, version, messages, font_facts, reason="failed", detail=detail)
    if not destination.is_file():
        return Rendering(
            None,
            version,
            messages,
            font_facts,
            reason="no-output",
            detail="resvg wrote no PNG",
        )
    return Rendering(destination.read_bytes(), version, messages, font_facts)


def _install_fonts(directory: Path) -> tuple[tuple[dict[str, object], ...], str | None]:
    """Install the exact bundled font set into resvg's isolated directory."""

    source = FONT_DIRECTORY / FONT_FILE
    licence = FONT_DIRECTORY / FONT_LICENSE_FILE
    try:
        data = source.read_bytes()
        licence_data = licence.read_bytes()
    except OSError as error:
        return (), f"bundled cover font unavailable: {error}"
    digest = sha256(data).hexdigest()
    licence_digest = sha256(licence_data).hexdigest()
    facts: tuple[dict[str, object], ...] = (
        {
            "family": "Atkinson Hyperlegible",
            "file": FONT_FILE,
            "license": "SIL Open Font License 1.1",
            "license_file": FONT_LICENSE_FILE,
            "license_sha256": licence_digest,
            "matches_expected_sha256": digest == FONT_SHA256,
            "sha256": digest,
            "source_commit": FONT_SOURCE_COMMIT,
            "style": "Regular",
            "version": "1.006",
        },
    )
    if digest != FONT_SHA256:
        return facts, "bundled cover font does not match its recorded SHA-256"
    if licence_digest != FONT_LICENSE_SHA256:
        return facts, "bundled cover font license does not match its recorded SHA-256"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        _ = (directory / FONT_FILE).write_bytes(data)
    except OSError as error:
        return facts, f"cannot stage bundled cover font: {error}"
    return facts, None


def installed_version(command: str) -> str | None:
    """Name the resvg that is actually on PATH, or nothing where none answered."""

    completed = run_dependency(command, ["--version"]).completed
    if completed is None or completed.returncode != 0:
        return None
    stated = completed.stdout.split()
    return stated[0] if stated else None
