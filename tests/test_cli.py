import json

from tests.public_cli import run_public_cli


def test_public_invocations_report_the_same_version() -> None:
    results = run_public_cli("--version")

    assert [(result.returncode, result.stdout, result.stderr) for result in results] == [
        (0, "0.1.0\n", ""),
        (0, "0.1.0\n", ""),
    ]


def test_public_invocations_expose_the_same_help_surface() -> None:
    results = run_public_cli("--help")

    assert [(result.returncode, result.stderr) for result in results] == [(0, ""), (0, "")]
    assert results[0].stdout == results[1].stdout
    assert "Prepare content for constrained reading environments." in results[0].stdout
    assert "--version" in results[0].stdout
    assert "hello" not in results[0].stdout


def test_public_invocations_list_available_profiles_as_stable_json() -> None:
    results = run_public_cli("profiles", "list", "--json")
    human_results = run_public_cli("profiles", "list")

    expected = [
        {
            "device": "iPhone 15 Pro",
            "id": "kindle-ios-personal-documents",
            "observed_software": {
                "kind": "application",
                "observed_at": "2026-08-27",
                "operating_system": {"name": "iOS", "version": "26.6"},
                "version": "7.65",
            },
            "profile_version": "0.3.0",
            "reader": "Kindle for iOS",
        },
        {
            "device": "Xteink X4",
            "id": "x4-crosspoint",
            "observed_software": {
                "kind": "firmware",
                "observed_at": "2026-08-16",
                "operating_system": None,
                "version": "1.4.1",
            },
            "profile_version": "0.4.0",
            "reader": "CrossPoint",
        },
    ]
    assert [(result.returncode, result.stderr) for result in results] == [(0, ""), (0, "")]
    assert [json.loads(result.stdout) for result in results] == [expected, expected]
    assert [(result.returncode, result.stderr) for result in human_results] == [(0, ""), (0, "")]
    expected_human = (
        "kindle-ios-personal-documents: iPhone 15 Pro / "
        "Kindle for iOS (profile 0.3.0, application 7.65 on iOS 26.6)\n"
        "x4-crosspoint: Xteink X4 / CrossPoint (profile 0.4.0, firmware 1.4.1)\n"
    )
    assert [result.stdout for result in human_results] == [expected_human, expected_human]


def test_public_invocations_show_one_assembled_profile_as_json() -> None:
    results = run_public_cli("profiles", "show", "x4-crosspoint", "--json")
    human_results = run_public_cli("profiles", "show", "x4-crosspoint")

    assert [(result.returncode, result.stderr) for result in results] == [(0, ""), (0, "")]
    profiles = [json.loads(result.stdout) for result in results]
    assert profiles[0] == profiles[1]
    profile = profiles[0]
    assert set(profile) == {
        "activation",
        "behaviour",
        "device",
        "id",
        "non_requirements",
        "observations",
        "profile_version",
        "reader",
        "requirements",
        "schema",
        "software",
    }
    assert profile["schema"] == "galley/device-profile/2"
    assert profile["profile_version"] == "0.4.0"
    assert [item["id"] for item in profile["requirements"]] == [
        "recorded-links-per-block",
        "footnote-href-length",
        "anchors-per-chapter",
        "footnotes-per-screen",
        "image-media-type",
        "png-decoding",
        "jpeg-decoding",
    ]
    assert [item["id"] for item in profile["non_requirements"]] == ["package-validity"]
    assert len(profile["behaviour"]) == 9
    assert len(profile["activation"]) == 8
    assert len(profile["observations"]) == 13

    href_requirement = profile["requirements"][1]
    assert href_requirement["limit"]["enforced"] == 96
    assert profile["software"]["queued_changes"] == [
        {
            "commit": "1582e70e",
            "constant": "FOOTNOTE_HREF_LEN",
            "from": 96,
            "landed": "2026-08-09",
            "note": "Unreleased main; a reason to re-check, never a profile value.",
            "to": 256,
        }
    ]
    retracted_claims = [
        claim
        for requirement in profile["requirements"]
        for claim in requirement["provenance"]
        if claim.get("status") == "retracted"
    ]
    assert len(retracted_claims) == 3
    assert [(result.returncode, result.stderr) for result in human_results] == [(0, ""), (0, "")]
    expected_human = (
        "x4-crosspoint: Xteink X4 / CrossPoint\n"
        "Profile 0.4.0; observed firmware 1.4.1\n"
        "Requirements: 7; non-requirements: 1\n"
        "Device Behaviour: 9; activations: 8; observations: 13\n"
        "Firmware rechecks: 1\n"
    )
    assert [result.stdout for result in human_results] == [expected_human, expected_human]


def test_unknown_profile_show_is_a_clean_invocation_error() -> None:
    results = run_public_cli("profiles", "show", "missing", "--json")

    assert [result.returncode for result in results] == [2, 2]
    assert [result.stderr for result in results] == ["", ""]
    expected = {
        "error": {
            "code": "unknown-profile",
            "message": "unknown Device Profile: missing",
            "profile": "missing",
        },
        "outcome": "invocation-error",
        "schema": "galley/profile-error/1",
    }
    assert [json.loads(result.stdout) for result in results] == [expected, expected]
