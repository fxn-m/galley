"""Four artifacts, four authors, and a disagreement none of them resolves by editing another.

A preparation completes, the agent records a concern against the Report's hash, Delivery confirms
the bytes landed, and a human later reads the book and disagrees with the agent.
All four remain true and byte-unchanged, because each answers a different question.
"""

import hashlib
import json
from pathlib import Path
from typing import cast

from scripts.checkrecords import ASSESSMENT, READING_RECORD, record_validator

from tests.support.crosspoint_server import crosspoint
from tests.support.delivery_fixtures import published, records
from tests.support.public_cli import run_cli
from tests.support.ready_fixtures import COMPLETED, ready_reports, report

PROFILE = {"id": "x4-crosspoint", "profile_version": "1.0.0"}


def worklist(document: dict[str, object]) -> list[dict[str, str]]:
    """Derive the skill's worklist from one Report, by the rule `assessment.md` states.

    Every observation whose `fired` is null and whose `applicability` is not false, plus every
    engaged preparation interlock, in the Report's own order. Nothing here judges: the owner comes
    from the observation's own `evidence`, which is how a device-judged entry stays the reader's.
    """

    entries: list[dict[str, str]] = []
    for entry in cast(list[dict[str, object]], document.get("observations", [])):
        if entry.get("fired") is None and entry.get("applicability") is not False:
            owner = "human" if entry.get("evidence") == "device-judged" else "agent"
            entries.append({"source": "observation", "name": str(entry["name"]), "owner": owner})
    preparation = cast(dict[str, object], document.get("preparation") or {})
    for transform in cast(list[dict[str, object]], preparation.get("transforms", [])):
        interlock = cast(dict[str, object], transform.get("interlock") or {})
        if interlock.get("engaged") is True:
            entries.append(
                {"source": "interlock", "name": str(transform["name"]), "owner": "agent"}
            )
    return entries


def test_the_worklist_is_derived_from_the_report_and_is_stable(tmp_path: Path) -> None:
    """The same Report always yields the same list, and each entry keeps its own owner."""

    workspace, _, _ = published(tmp_path)
    document = ready_reports(workspace)[0]

    first = worklist(document)
    assert first == worklist(json.loads(json.dumps(document)))
    assert first, "a Report the CLI cannot fully judge must leave the agent a worklist"
    # The rule sorts entries by their own Observation Evidence, so a `device-judged` one would
    # land in the reader's lane. `x4-crosspoint` activates none, which is why every entry here is
    # the agent's — a fact about this profile's activation, not about the registry entry.
    assert {entry["owner"] for entry in first} == {"agent"}
    assert not any(entry["name"] == "pagination-granularity" for entry in first)


def test_the_four_artifacts_may_disagree_without_overwriting_one_another(tmp_path: Path) -> None:
    """A clean build, a worried agent, a confirmed Delivery and a contented reader, all at once."""

    workspace, artifact, environment = published(tmp_path)
    report_path = next((workspace / "ready/evidence").glob("*/report.json"))
    document = report(report_path.read_text("utf-8"))
    assert document["outcome"] == "completed"
    verdict = cast(dict[str, object], document["reading_verdict"])
    assert verdict == {"value": "not_tested", "predicted": None}
    report_bytes = report_path.read_bytes()

    assessment = _assessment(report_path, document)
    record_validator(ASSESSMENT)[1].validate(assessment)
    assessment_path = tmp_path / "assessment.json"
    _ = assessment_path.write_text(json.dumps(assessment, indent=2), encoding="utf-8")

    with crosspoint() as (host, device):
        results = run_cli(
            "deliver", str(artifact), "--json", "--host", host, environment=environment
        )
        assert device.files[artifact.name] == artifact.stat().st_size
    assert results.returncode == COMPLETED
    record_path = _delivered_record(workspace)
    delivery = report(record_path.read_text("utf-8"))
    assert delivery["outcome"] == "delivered"
    delivery_bytes = record_path.read_bytes()

    reading = _reading_record(report_path, document, delivery, assessment_path)
    record_validator(READING_RECORD)[1].validate(reading)

    # The disagreement is the point: the CLI completed, the agent predicted poor, Delivery
    # confirmed, and the reader found it acceptable. Each artifact still says what it said.
    assert assessment["predicted_verdict"] == "poor"
    assert reading["reading_verdict"] == "acceptable"
    assert reading["reading_verdict"] != assessment["predicted_verdict"]
    assert report_path.read_bytes() == report_bytes
    assert record_path.read_bytes() == delivery_bytes
    assert json.loads(report_bytes)["reading_verdict"] == {"value": "not_tested", "predicted": None}


def test_neither_authored_record_can_sign_the_others_name() -> None:
    """The separation is structural: neither shape has a field for the other layer's answer."""

    assessment, _ = record_validator(ASSESSMENT)
    reading, _ = record_validator(READING_RECORD)

    assert "reading_verdict" not in cast(dict[str, object], assessment["properties"])
    assert "predicted_verdict" not in cast(dict[str, object], reading["properties"])
    assert "report_sha256" in cast(list[object], assessment["required"])
    for anchor in ("artifact_sha256", "delivery_record_id", "optimize_disabled"):
        assert anchor in cast(list[object], reading["required"])


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _delivered_record(workspace: Path) -> Path:
    """The immutable record of the invocation that uploaded the Ready Artifact."""

    written = sorted((workspace / "delivery").glob("*.json"))
    assert len(written) == len(records(workspace))
    delivered = [
        path for path in written if report(path.read_text("utf-8"))["outcome"] == "delivered"
    ]
    assert len(delivered) == 1, [path.name for path in written]
    return delivered[0]


def _assessment(report_path: Path, document: dict[str, object]) -> dict[str, object]:
    entries = worklist(document)
    return {
        "schema": ASSESSMENT,
        "assessed_by": "the scenario",
        "assessed_at": "2026-08-19T12:00:00Z",
        "report_path": str(report_path),
        "report_sha256": _digest(report_path),
        "artifact_sha256": str(cast(dict[str, object], document["artifact"])["sha256"]),
        "profile": PROFILE,
        "worklist": entries,
        "findings": [
            {
                "observation": "boundary-chrome-presence",
                "fired": True,
                "central_content": True,
                "basis": "Navigation furniture reads as body text at the head of every chapter.",
            }
        ],
        "outstanding": [entry for entry in entries if entry["owner"] == "human"],
        "predicted_verdict": "poor",
        "predicted_basis": "Contamination on Central Content, if the chrome reads as it looks.",
    }


def _reading_record(
    report_path: Path,
    document: dict[str, object],
    delivery: dict[str, object],
    assessment_path: Path,
) -> dict[str, object]:
    artifact = cast(dict[str, object], document["artifact"])
    device = cast(dict[str, object], delivery["device"])
    return {
        "schema": READING_RECORD,
        "reader": "the scenario's human",
        "read_on": "2026-08-20",
        "artifact_sha256": str(artifact["sha256"]),
        "ready_artifact_path": str(artifact["path"]),
        "report_path": str(report_path),
        "report_sha256": _digest(report_path),
        "delivery_record_id": str(delivery["record_id"]),
        "assessment_sha256": _digest(assessment_path),
        "profile": PROFILE,
        "firmware": str(device["firmware"]),
        "optimize_disabled": True,
        "observations": [
            {
                "observation": "boundary-chrome-presence",
                "fired": True,
                "central_content": False,
                "basis": "The chrome is there and is skimmed past in a line; it costs nothing.",
            }
        ],
        "reading_verdict": "acceptable",
        "note": "Read on the panel. The prediction was reasonable and the panel disagreed.",
    }
