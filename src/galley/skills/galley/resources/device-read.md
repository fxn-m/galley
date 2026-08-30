# The device-read protocol

A Reading Verdict comes from a human reading the finished book on the device — never from a
mechanically successful build or a confirmed Delivery. This is what a read requires, what the
reader records, and why it is a fourth artifact rather than an edit to the other three.

## Three preconditions

A read that is missing any of these is not evidence about Galley's output, so it does not happen
until all three hold:

1. **A Ready Artifact.** The book is an artifact `prepare --ready` published: audited, immutable,
   and described by a Report in its evidence bundle. A file rebuilt for the occasion, or edited
   after publication, is a different book from the one any Report describes.
2. **Its Delivery Record.** The `galley/delivery-record/2` a confirmed Delivery persisted — its
   `record_id`, the resolved device, its firmware and mode, and the destination the bytes landed
   at. That record is what says these bytes reached this device, confirmed by a fresh listing
   rather than by a command that merely exited cleanly.
3. **Optimize disabled.** Delivery uploads the audited artifact's exact bytes, and CrossPoint's
   Optimize would rewrite them on the device. With Optimize off, the artifact hash in the Report
   still names the bytes under the reader's eyes; with it on, the reader is reading something no
   Report audited.

Neither the Report nor the Delivery Record is regenerated for the read. A device read that cannot
find both for the exact artifact hash on the device has lost its anchor, and the reader says so
rather than reading a book whose provenance is unknown.

## The reading record

One JSON document per read, against [`galley/reading-record/1`](reading-record.schema.json),
written beside the Report and never inside it.

```json
{
  "schema": "galley/reading-record/1",
  "reader": "reader-name",
  "read_on": "2026-08-19",
  "artifact_sha256": "b7042c9e58fd13a6e0c47b825da916f3c8e02b57d94a1f6308cbe27d54a9f81b",
  "ready_artifact_path": "workspace/ready/artifacts/a-short-essay.epub",
  "report_path": "workspace/ready/evidence/6b1e/report.json",
  "report_sha256": "3f8a1d94c2be07a5518d6e4b0cf39a72d15b8e6034ca7f92be1d05c8a4739e16",
  "delivery_record_id": "0f5c7a2e91d4",
  "assessment_sha256": "c41ab6035e7d2f8916b0a4de5c7238091fbe64a7d052c9836be1470a2fd58c93",
  "profile": { "id": "x4-crosspoint", "profile_version": "1.0.0" },
  "firmware": "1.4.1",
  "optimize_disabled": true,
  "observations": [
    {
      "observation": "pagination-granularity",
      "fired": false,
      "central_content": false,
      "basis": "Page turns landed on paragraph boundaries throughout; nothing about the length made it hard to keep a place. No Report carries this one — it exists only on the panel."
    },
    {
      "observation": "diagram-text-legibility",
      "fired": true,
      "central_content": false,
      "basis": "The diagram labels are indeed unreadable, but the prose states the same relationships, so the diagrams illustrate rather than carry."
    }
  ],
  "reading_verdict": "acceptable",
  "note": "Read end to end on the panel. The agent predicted poor on the diagrams; on the device they turn out to be decoration."
}
```

## Why the fields are these

- **The three anchors** — `artifact_sha256`, `report_sha256` and `delivery_record_id` — tie the
  read to one built, described and delivered book. `assessment_sha256` names the agent assessment
  the reader had in front of them, or is `null` where there was none; naming it records what the
  read may disagree with, and never edits it.
- **`profile.profile_version` and `firmware`** say what hardware and software the read happened
  on. Every device claim is empirical, and a verdict on unnamed firmware cannot be checked later.
- **`read_on` and `reader`** are the date and the person. A Reading Verdict is somebody's, and
  which day it was taken on decides which firmware and which profile it can speak for.
- **`observations`** are the entries the reader settled on the reading surface — any Registry entry,
  including ones an agent or the CLI also answered. A disagreement here is information, not a
  correction to be pushed back into the Report.
- **`reading_verdict`** is the whole point, and it has four values. `not_tested` is not among
  them: this record exists because a read happened, and a case with no reading record is what
  `not_tested` means.

## What the record does not do

It does not amend the Report, the [agent assessment](assessment.md) or the Delivery Record. Those
are written once and referenced by hash or id afterwards. The Verdict is the human's alone and is
the only layer that can say a book reads well — but it says so as a fourth answer standing beside
the other three, not by overwriting any of them.
