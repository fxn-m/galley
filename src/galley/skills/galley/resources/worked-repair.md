# A worked repair: Paul Graham's hand-rolled endnotes

The essay at `paulgraham.com/greatwork` carries 29 endnote references and yields **0** notes,
by URL and as extractor-produced Markdown alike. Its brackets are a fact about one website, so
the CLI will never learn them. This is the whole repair, end to end.

## 1. Inspect, and keep the evidence

```
galley inspect https://paulgraham.com/greatwork \
  --profile x4-crosspoint --json --evidence-dir greatwork.inspection
```

You now hold `report.json`, `canonical-document.json`, `preservation-baseline.txt` and
`extraction.html`. Keep them somewhere `prepare` will not later own: preparation writes its own
evidence directory, named after the EPUB's stem, and it refuses rather than write over a file it
is reading. Read the Report first. If link stripping reports its interlock engaged and
`extraction.footnote_recovery` reports `not-recognised`, this is the shape.

## 2. Confirm the convention

Match what you see against `repair-conventions.yaml` before writing anything. The entry states
the pairing key — the marker's **visible digit**, on both carriers — and why an id or `href`
key pairs nothing: extraction has already destroyed every in-page anchor target.

Read the digits out of `greatwork.inspection/preservation-baseline.txt`. Each one appears twice: once at its
reference and once at its definition. If a digit appears once, or a reference has no definition,
stop and report it rather than guessing. A blank note is worse than no note.

## 3. Repair the Canonical Document

Copy `canonical-document.json`, change only `pandoc`, and leave `schema`, `title`, `author`,
`source_url`, `warnings` and the Pandoc API version exactly as they are.

Working on the native AST, for each marker digit *n*:

1. Find the reference inline in the body — a `Link` or `Str` whose visible text is `[n]`.
2. Find its definition in the notes section — the block introduced by the same `[n]`.
3. Replace the reference inline with `{"t": "Note", "c": [<the definition's blocks>]}`, with the
   introducing marker removed from the note's own text.
4. When every reference has been paired exactly once, delete the notes section — its heading and
   its definition blocks — from the body.

Pair all 29 or none. A partial repair ships a reader a reference that leads nowhere, so Galley
refuses the entire recovery when any pair is incomplete.

Repair here, never on a generated EPUB. By the time an EPUB exists the interlock has already
fired and the link-stripping decision is made, so editing the book leaves the damage in place
and hides it.

## 4. Declare what the repair consumes

The digits survive: each becomes its reference number and its "Footnote N." label in the built
book. The notes section's own heading word does not. Declare exactly that:

```
echo '{"Notes": 1}' > expected-missing.json
```

Declaring more than the repair truly consumes is how real loss hides. If you are unsure, run
step 5 without the file first and read `tokens.unexpected_missing`.

## 5. Resubmit through `prepare`

```
galley prepare https://paulgraham.com/greatwork \
  --profile x4-crosspoint --output greatwork.epub --json \
  --inspection-report greatwork.inspection/report.json \
  --canonical-document greatwork-repaired.json \
  --preservation-baseline greatwork.inspection/preservation-baseline.txt \
  --expected-missing-tokens expected-missing.json
```

This publishes `greatwork.epub` beside a fresh `greatwork.galley` evidence directory, which is
why the inspection evidence was kept apart: had the two been the same directory, `prepare` would
have refused at `output-is-input` rather than run.

All three Repair Inputs go together; two of them is an invalid invocation, not a refusal. Galley
checks the Device Profile, the source, the baseline's digest and the Pandoc API version against
the inspection before the repaired document contributes a single fact, then takes it down the
same pipeline an unrepaired document goes down.

## 6. Verify

Read the finished Report:

- `canonical_document.repair.changed` is `true`, and the chain names the original canonical form,
  the repaired one, the baseline and the source.
- `preparation.transforms` shows note conversion fired, with 29 notes and 29 note documents.
- `artifact.text_preservation.tokens.unexpected_missing` is empty, and `declared` shows the one
  token you declared.
- `artifact.links.footnote_references.unresolved` is `0`.

If `unexpected_missing` names ordinary prose rather than apparatus, the repair ate text. Fix the
repair; do not widen the declaration.

## The Markdown carrier

Identical, with one difference: `galley inspect greatwork.md --evidence-dir
greatwork.inspection ...`, and the digit is read from the link text because Markdown carries no anchors at all. The matching key, the target, the
declaration and every verification step are the same — which is why this is one Repair
Convention naming two shapes rather than two conventions.

## What this repair does not become

It stays yours, permanently, however often the source recurs. If several *unrelated* sources
need the same hand-fix, that is a prompt to look for something general in the extractor or the
format — and whatever general thing you find enters on its own generality, never as this repair
moved inward.
