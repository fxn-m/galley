from copy import deepcopy
from typing import cast

from galley.profile.loading import load_profile
from galley.report.envelope import ReportAssembly
from galley.report.render import render_report


def test_a_resolved_report_names_observed_reader_software_generically() -> None:
    report = ReportAssembly.completed("inspect", load_profile("x4-crosspoint"))

    assert report["profile"] == {
        "id": "x4-crosspoint",
        "observed_software": {
            "kind": "firmware",
            "observed_at": "2026-08-16",
            "operating_system": None,
            "version": "1.4.1",
        },
        "profile_version": "0.4.0",
        "requested": "x4-crosspoint",
        "resolved": True,
    }


def test_an_application_report_carries_its_operating_system_without_firmware_language() -> None:
    profile = deepcopy(load_profile("x4-crosspoint"))
    profile["id"] = "application-reader"
    profile["profile_version"] = "1.0.0"
    profile["software"] = {
        "kind": "application",
        "version": "7.18",
        "operating_system": {"name": "iOS", "version": "18.6"},
        "observed_at": "2026-08-27",
        "queued_changes": [],
    }

    report = ReportAssembly.completed("inspect", profile)

    observed = cast(
        dict[str, object], cast(dict[str, object], report["profile"])["observed_software"]
    )
    assert observed == {
        "kind": "application",
        "observed_at": "2026-08-27",
        "operating_system": {"name": "iOS", "version": "18.6"},
        "version": "7.18",
    }
    rendered = render_report(report)
    assert "(application 7.18 on iOS 18.6)" in rendered
    assert "firmware 7.18" not in rendered
