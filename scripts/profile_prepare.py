"""Profile one reproducible minimal Markdown preparation."""

from __future__ import annotations

import argparse
import json
import pstats
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import cast

SOURCE = "# Minimal preparation\n\nOne paragraph for the profiling path.\n"


def main() -> int:
    """Run the installed module under cProfile and report workflow and wall-clock timings."""

    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("profile", type=Path, help="cProfile data file to replace")
    _ = parser.add_argument(
        "--summary-only", action="store_true", help="Read an existing profile without preparing"
    )
    arguments = parser.parse_args()
    profile = cast(Path, arguments.profile).resolve()
    if cast(bool, arguments.summary_only):
        print(json.dumps(_profile_times(profile), sort_keys=True))
        return 0
    profile.parent.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(prefix="galley-profile-") as directory:
        workspace = Path(directory)
        source = workspace / "minimal.md"
        output = workspace / "minimal.epub"
        source.write_text(SOURCE, encoding="utf-8")
        command = (
            sys.executable,
            "-m",
            "cProfile",
            "-o",
            str(profile),
            "-m",
            "galley",
            "prepare",
            str(source),
            "--profile",
            "x4-crosspoint",
            "--output",
            str(output),
            "--json",
        )
        started = perf_counter()
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        elapsed = perf_counter() - started

    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        sys.stderr.write(result.stdout)
        return result.returncode
    report = cast(dict[str, object], json.loads(result.stdout))
    galley = cast(dict[str, object], report["galley"])
    summary = {
        **_profile_times(profile),
        "duration_ms": galley["duration_ms"],
        "elapsed_seconds": round(elapsed, 6),
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


def _profile_times(profile: Path) -> dict[str, object]:
    """Separate Galley work from time waiting for external dependency processes."""

    statistics = pstats.Stats(str(profile))
    entries = cast(
        dict[tuple[str, int, str], tuple[int, int, float, float, dict[object, object]]],
        getattr(statistics, "stats"),
    )
    external_wait = sum(
        values[3]
        for (filename, _, function), values in entries.items()
        if filename.endswith("selectors.py") and function == "select"
    )
    profiled = cast(float, getattr(statistics, "total_tt"))
    return {
        "external_wait_seconds": round(external_wait, 6),
        "in_process_seconds": round(profiled - external_wait, 6),
        "profile": str(profile),
        "profiled_seconds": round(profiled, 6),
    }


if __name__ == "__main__":
    raise SystemExit(main())
