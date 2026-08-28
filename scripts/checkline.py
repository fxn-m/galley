"""Keep project files below a small, explicit line limit."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

DEFAULT_LIMIT = 300
DEFAULT_PATHS = (
    Path("src"),
    Path("tests"),
    Path("scripts"),
    Path("profiles"),
    Path("AGENTS.md"),
    Path("README.md"),
    Path("pyproject.toml"),
)
CHECKED_SUFFIXES = {".json", ".md", ".py", ".toml", ".txt", ".yaml", ".yml"}
SKIPPED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}


@dataclass(frozen=True)
class FileLength:
    """A measured project file."""

    path: Path
    lines: int


def iter_files(paths: Iterable[Path]) -> Iterator[Path]:
    """Yield checked files below the supplied paths."""

    for path in paths:
        if _is_skipped(path):
            continue
        if path.is_file() and _is_checked_file(path):
            yield path
        elif path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and _is_checked_file(child) and not _is_skipped(child):
                    yield child


def measure_files(paths: Iterable[Path]) -> list[FileLength]:
    """Count lines for all checked files."""

    return [FileLength(path=path, lines=_count_lines(path)) for path in iter_files(paths)]


def find_violations(paths: Iterable[Path], *, max_lines: int = DEFAULT_LIMIT) -> list[FileLength]:
    """Return files longer than the configured limit."""

    return [file for file in measure_files(paths) if file.lines > max_lines]


def main(argv: Sequence[str] | None = None) -> int:
    """Run the file-length check."""

    parser = argparse.ArgumentParser(description="Fail when project files exceed a line limit.")
    parser.add_argument("paths", nargs="*", type=Path, default=list(DEFAULT_PATHS))
    parser.add_argument("--max-lines", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args(argv)

    if args.max_lines < 1:
        parser.error("--max-lines must be at least 1")

    paths: list[Path] = args.paths
    max_lines: int = args.max_lines
    measurements = measure_files(paths)
    violations = [file for file in measurements if file.lines > max_lines]

    if violations:
        for violation in violations:
            print(
                f"checkline: {violation.path}: {violation.lines} lines > {max_lines}",
                file=sys.stderr,
            )
        return 1

    print(f"checkline: OK ({len(measurements)} files <= {max_lines} lines)")
    return 0


def _is_checked_file(path: Path) -> bool:
    return path.suffix in CHECKED_SUFFIXES


def _is_skipped(path: Path) -> bool:
    return any(part in SKIPPED_PARTS for part in path.parts)


def _count_lines(path: Path) -> int:
    with path.open("rb") as file:
        return sum(1 for _line in file)


if __name__ == "__main__":
    raise SystemExit(main())
