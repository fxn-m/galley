# Reading a Galley Report

One envelope, five fact categories, and evaluation joined onto them.

## Envelope

- `galley` — version, command, run id, timings, report schema, and the exact dependency
  versions this run observed.
- `outcome` — `completed` or `refused`.
- `refusal` — `null` on a completed run. Otherwise its `boundary`, the `stage` it stopped at, a
  `summary`, the `fact` behind it, `artifact_written: false`, and `basis_for_inference` where
  Galley inferred the refusal rather than observing it.
- `profile` — what was requested and what resolved.
- `warnings` — construction events that left no recomputable trace. Nothing else appears here.
- `reading_verdict` — `not_tested` until a human has read the book on the device. Your estimate
  is a Predicted Verdict and belongs beside the Report, never inside it.

## The five fact categories

| Category | What it describes |
|---|---|
| `source` | What was named and read: kind, path or URL, size, digest, encoding, parser. |
| `extraction` | Present only for an Article-Like Page: the extractor's own facts, the footnote recovery result, and Galley's own measured word count. |
| `canonical_document` | The parsed document: title, author, Pandoc API version, block and constructor counts, Unsupported Content, the Preservation Baseline's digest, and — on a repaired run — the `repair` chain. |
| `preparation` | What `prepare` did: every transform and whether it fired, packaging facts, image records. |
| `artifact` | The built or audited book: bytes, digest, package and navigation facts, links, images, conformance, and Text Preservation. |

## Every number carries its basis

- `measured` — this run took the measurement.
- `projected` — inferred about a future artifact, with a stated `relation` to the measurable
  value. A lower bound already above a limit proves the limit is broken; one below it proves
  nothing.
- `reported` — a dependency's number, or a fact inherited from another run. A repaired
  preparation inherits the extraction facts it did not re-establish, so they arrive `reported`.

## Observations are tri-state

`fired` is `true`, `false`, or `null`. `null` means the CLI is not the judging layer and the
judgement is outstanding — yours, from the primitives and previews beside it, or a human's after
a device read. A `null` is a worklist entry. It is never a `false`.

Each entry's own `evidence` field says whose it is, and `applicability: false` takes it off the
list. [The worklist](assessment.md) states the derivation and the assessment it feeds.

## The worklist a repair starts from

Two Report facts point at a document with footnotes hiding in it:

1. The link-stripping transform reports its interlock **engaged**: in-book links are present and
   no Footnote Apparatus was recognised, so cross-reference stripping is held back.
2. `extraction.footnote_recovery` reports `not-recognised` (nothing was there to recover) or
   `skipped` with the condition that stopped it (the shape was there and could not be paired).

That pair is the trigger. Without it, a successful document needs no inspection from you.

## How far the figures were reduced

`preparation.images.reduction` summarises the per-image scales that have always been in
`preparation.images.records`, so a document that leans on pictures is visible without arithmetic
across every one of them. It counts every image reference except the cover, states how many are
smaller than their source, and gives the minimum, median and maximum percentage — `null` where the
document carries no figure. The percentage is the packaged width against the source width.

It is a measurement and not a verdict. Nothing in it predicts whether a reduced figure is legible,
and the heads-up you build from it
[says what was measured rather than what will happen](assessment.md).

## Text Preservation

`artifact.text_preservation` compares the retained Preservation Baseline against the built book,
order-free and one-directional, at word level. Restructuring reads as a move; only disappearance
reads as loss. Read four fields:

- `claimed` — whether Galley makes the claim at all. `false` with a `reason` and a `detail` means
  it does not: either `audit` had no retained baseline, or the source reader discarded content
  before the baseline was taken. The measurement below is still there and still true of what
  Galley was handed; it is narrower than the claim would be. `discarded` names what the reader
  dropped, in its own words.
- `tokens.declared` — every expected-missing declaration this run was given, whether or not it
  fired.
- `tokens.expected_missing` — the declarations that actually materialised.
- `tokens.unexpected_missing` — undeclared loss. `prepare` refuses on it.
- `characters` — a stricter second pass, not authoritative.

The check covers text alone. It is blind to links, images and formatting, and it is not evidence
that a book reads well. It is also blind behind its own baseline: the baseline is rendered from
the Canonical Document, so anything the reader dropped producing that document is outside it,
which is what `claimed: false` with `source-reader-discarded-content` is telling you.
