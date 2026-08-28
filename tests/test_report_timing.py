from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from galley.output.policy import apply_report_output_policy
from galley.report.clock import Clock
from galley.report.envelope import ReportRun, unknown_profile_report


def test_one_run_clock_spans_profile_resolution_and_output_policy() -> None:
    moments = iter(
        (
            datetime(2026, 8, 17, 12, 0, 0, tzinfo=UTC),
            datetime(2026, 8, 17, 12, 0, 1, tzinfo=UTC),
            datetime(2026, 8, 17, 12, 0, 4, tzinfo=UTC),
        )
    )
    clocks = iter((1_000_000, 2_000_000, 5_000_000))
    clock = Clock(utc_now=lambda: next(moments), monotonic_ns=lambda: next(clocks))

    run = ReportRun.start(clock)
    report = unknown_profile_report("inspect", "missing", ["x4-crosspoint"], run=run)
    initial_galley = cast(dict[str, object], report["galley"])
    emission = apply_report_output_policy(
        report,
        source=Path(__file__),
        output=None,
        overwrite=False,
        run=run,
    )
    final_galley = cast(dict[str, object], emission.report["galley"])

    assert initial_galley["started_at"] == "2026-08-17T12:00:00.000Z"
    assert initial_galley["finished_at"] == "2026-08-17T12:00:01.000Z"
    assert initial_galley["duration_ms"] == 1
    assert final_galley["started_at"] == "2026-08-17T12:00:00.000Z"
    assert final_galley["finished_at"] == "2026-08-17T12:00:04.000Z"
    assert final_galley["duration_ms"] == 4
