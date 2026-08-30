# Your worklist, and the assessment you record

The Report is the CLI's. The Reading Verdict is a human's. Between them, when a later eval or
device-read needs one, is an **assessment** recorded beside the Report and referencing its hash.
Routine Assisted Preparation and Inbox conversion settle flaggable items and say material caveats
without writing that file. This is how the worklist is derived and what an assessment contains
when one is written.

## The worklist is derived, not chosen

A Report already carries everything that decides what is outstanding, so read the worklist off it
rather than deciding which documents look interesting. Two rules produce it, and the same Report
always produces the same list:

1. **Every observation whose `fired` is `null`, unless its `applicability` is `false`.** The CLI
   sets `null` for exactly the observations assigned to another layer — never as a shrug — so a
   `null` is an open judgement with a name. Each entry's `evidence` field says whose it is:
   `flaggable` is yours, and `device-judged` belongs to the reader on the panel.
2. **Every engaged preparation interlock.** Link stripping reports
   `interlock.engaged: true` when the document carries in-book links and no recognised Footnote
   Apparatus. Paired with `extraction.footnote_recovery` at `not-recognised` or `skipped`, that is
   the repair trigger [the worked repair](worked-repair.md) walks through.

The list is in the Report's own observation order, which is the Registry's. Nothing else is on it:
a completed run with no `null` observation and no engaged interlock is finished, and saying so is
the honest report rather than a thin one.

An entry you cannot settle stays outstanding under its owner's name. A `device-judged` observation
is not something to estimate into `false` — that is the same move the CLI is forbidden to make.

The rule holds for any Device Profile, but the lanes are not always both occupied. The
`x4-crosspoint` profile activates thirteen Registry observations and none of them is
`device-judged`, so every entry it yields today is yours; a profile that activates one would put
that entry in the reader's lane instead, and it would wait for the device read.

## What you settle it from

The evidence directory beside the Report holds the deterministic previews. Judge
`diagram-text-legibility` from the prepared-pixel preview and `colour-meaning-collapse` by
comparing the source and greyscale previews. Where no evidence settles an entry, it stays
outstanding — a finding needs a basis, and "it looked fine" is not one.

## The heads-up about figures

One thing you say out loud, whatever you end up recording. `preparation.images.reduction` states
how far this document's figures were reduced to fit the panel — how many the book carries, how many
shrank, and the minimum, median and maximum percentage — so you can see at a glance what a document
leans on without walking twenty-eight image records to work it out.

Where a work leans on its figures and they were reduced a long way, tell the reader in one plain
sentence before they start. A heads-up, not a warning, and not a failure:

> By the way, this article leans on its diagrams — seven of them, all reduced to about an eighth of
> their original size to fit the panel. That sometimes reads fine and sometimes does not. Worth a
> look before you settle in.

Three things keep that sentence honest.

**It predicts nothing.** No number in the Report says whether a reduced figure is legible. Two
device reads illustrate why: the document the reader called "very clear" carried
*more* figures, reduced *harder*, than the one they called "just too small". State what was
measured and let them look.

**There is no threshold, deliberately.** Inventing one here is the move the CLI itself is forbidden
to make. Judge it, and judge it from the prepared-pixel previews in the evidence directory — the
same ones that settle `diagram-text-legibility`.

**Say it rarely.** A heads-up on most documents is noise, and worse than silence. A book with two
pictures that both fit gets none.

## The assessment record

One JSON document per Report, against
[`galley/agent-assessment/1`](agent-assessment.schema.json). Its `report_sha256` is the SHA-256 of
the exact Report bytes you read, which is what makes the assessment attributable to one immutable
run: re-preparing the document produces a different Report and needs a new assessment, rather than
quietly inheriting this one.

```json
{
  "schema": "galley/agent-assessment/1",
  "assessed_by": "claude-opus-5",
  "assessed_at": "2026-08-19T11:24:06Z",
  "report_path": "workspace/ready/evidence/6b1e/report.json",
  "report_sha256": "3f8a1d94c2be07a5518d6e4b0cf39a72d15b8e6034ca7f92be1d05c8a4739e16",
  "artifact_sha256": "b7042c9e58fd13a6e0c47b825da916f3c8e02b57d94a1f6308cbe27d54a9f81b",
  "profile": { "id": "x4-crosspoint", "profile_version": "1.0.0" },
  "worklist": [
    { "source": "observation", "name": "colour-meaning-collapse", "owner": "agent" },
    { "source": "observation", "name": "diagram-text-legibility", "owner": "agent" },
    { "source": "interlock", "name": "link-stripping", "owner": "agent" }
  ],
  "findings": [
    {
      "observation": "diagram-text-legibility",
      "fired": true,
      "central_content": true,
      "basis": "The two architecture diagrams carry the argument, and their axis labels are unreadable in the prepared-pixel preview."
    }
  ],
  "outstanding": [
    { "source": "interlock", "name": "link-stripping", "owner": "agent" }
  ],
  "predicted_verdict": "poor",
  "predicted_basis": "A legibility observation fires on Central Content, which the rubric places at poor. This is my estimate, not a read."
}
```

Four things about that shape are the point of it:

- `report_sha256` anchors every judgement to one immutable run.
- `findings` admits only the five flaggable observation names. The computable ones are the CLI's
  measurements and the `device-judged` one is the reader's; restating either here would be a
  second answer to a settled question.
- `predicted_verdict` is labelled a prediction wherever it is shown, and `excellent` is not one of
  its values: the rubric gates that on a real device read, so the shape refuses the estimate
  rather than trusting you not to make it.
- There is no field for a Reading Verdict, and the shape refuses one. That is the structural
  version of the boundary rather than a promise to respect it.

## Four artifacts, four authors

| Artifact | Author | Says |
|---|---|---|
| Preparation Report | the CLI | what was measured, and whether it refused |
| Agent assessment | you | flaggable findings and a Predicted Verdict, against a Report hash |
| Delivery Record | the CLI | that these exact bytes reached this exact device |
| Reading record | a human | how the book actually read — see [the device-read protocol](device-read.md) |

Each one is written once and referenced afterwards by hash or id. They can legitimately disagree:
a run completes cleanly, you predict `poor`, Delivery confirms, and the reader finds it
`acceptable`. All four stay true, because each answers a different question. Reconciling them by
editing one is how the answer to the interesting question gets lost.
