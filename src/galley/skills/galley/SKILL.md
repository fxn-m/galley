---
name: galley
description: Prepare documents for constrained reading environments with the Galley CLI. Use when inspecting, preparing or auditing Markdown or an Article-Like Page for a Device Profile, preparing a Kindle-ready EPUB, reading a Galley Report, or repairing a document Galley's tooling misreads before resubmitting it.
---

# Galley

Galley turns supported reading material into EPUBs that work on a constrained reading device.
Three layers do three jobs, and this skill is the middle one:

- **The CLI** owns deterministic, general behaviour and every Report Fact and refusal.
- **You** orchestrate, judge what the CLI leaves outstanding, and write Bespoke Repairs.
- **A human** records the Reading Verdict, after reading the book on the device.

Detail lives in bounded resources rather than in this file:
[the command contract](resources/cli-contract.md),
[reading a Report](resources/report-fields.md),
[leading an Assisted Preparation](resources/assisted-preparation.md),
[Repair Conventions](resources/repair-conventions.yaml),
[a complete worked repair](resources/worked-repair.md),
[localising a document's remote images](resources/localisation.md),
[authoring profile-directed Cover Artwork](resources/cover-artwork.md),
[handing a Ready Artifact to a Kindle user](resources/kindle-ios-handoff.md),
[the "Galley my inbox" run](resources/galley-my-inbox.md),
[your worklist and the assessment you record](resources/assessment.md), and
[the device-read protocol](resources/device-read.md).

## Choosing a command

| You want to | Run |
|---|---|
| Know what a source carries before building | `galley inspect SOURCE --profile PROFILE --json` |
| Build the book | `galley prepare SOURCE --profile PROFILE --output PATH --json` |
| Assess an EPUB you did not build | `galley audit EPUB --profile PROFILE --json` |
| Bring a Markdown source's remote images onto this machine | `galley localise SOURCE --profile PROFILE --evidence-dir DIR --json` |

Always pass `--json` and read the Report. The human rendering is the same data, shorter.

## Confirm the Device Profile before conversion work

For every one-source conversion, run `galley profiles list --json`, show the available reader and
device choices, and ask the user to confirm which one this artifact is for. Do this before
`inspect`, profile-directed cover work, Localisation or `prepare`. Even when the request names a
target, restate the reader, device and profile id and take one short confirmation so the chosen
constraints are visible before work begins.

Never infer the profile from an `[x4-crosspoint]` configuration table, setup answers, available
hardware, a previous conversion, the source or the order returned by `profiles list`. Workspace
configuration can make delivery possible; it does not choose what is being prepared. When a
conversion resumes after setup, retain a profile confirmation already made for that request;
otherwise ask before resuming profile-specific work.

## Assisted Preparation

When the user chooses one source and wants the complete agent-guided journey to a Ready Artifact,
follow [the Assisted Preparation contract](resources/assisted-preparation.md).
It begins with inspection and gives the user one visible account of the classification, repair,
cover, Localisation, preparation and assessment work around the existing public commands.

## When the Workspace is not configured yet

The Workspace-aware commands resolve one Galley Workspace and read the `galley.toml` inside it.
`galley config validate --json` is the read-only way to find out what that file says: exit `0`
means it reads, and a refusal at `workspace-configuration-missing`,
`invalid-workspace-configuration`, `unknown-configuration-key`,
`unsupported-configuration-version`, `duplicate-inbox-name`, `inbox-unavailable` or
`workspace-location-unusable` means configuration is what stopped the run rather than the
document.

Hand that user to the `galley-setup` skill, which owns the question set and authors the file.
Choosing a Workspace path for them, or editing `galley.toml` from here, would put configuration
they have not seen behind everything Galley later reports.

## When an external command is unavailable

A `dependency-unavailable` refusal, or a missing Pandoc, Defuddle, EPUBCheck or resvg command named
inside another refusal, hands the environment to `galley-setup`. That skill inventories the pinned
release requirements, plans and performs any approved installation, and verifies all four commands.
Resume the original reading request after setup reports them ready; raw installation commands are
not a task to pass on to the user.

## "Galley my inbox"

One request runs the whole Workspace: validate configuration, check the Inbox once, prepare every
routine candidate, and present a finite set of Delivery Plans for one approval.
[The end-to-end guide](resources/galley-my-inbox.md) walks all six phases; the shape is:

1. **Validate.** `galley config validate --json`. A configuration boundary hands the user to
   `galley-setup` (above); resume once it validates.
2. **Check.** `galley inbox check --json`, once. An unavailable Inbox's candidates are reported as
   unknown, not as absent.
3. **Prepare.** Build every unambiguous `new` or `changed` Markdown candidate with `--ready` and
   its `--expected-source-hash`, without a per-file prompt. Identity ambiguity, a consequential
   repair, or a structured refusal stops that one candidate alone, its evidence kept.
4. **Assess.** Settle the worklist and record your judgement and Predicted Verdict in a
   [separate assessment](resources/assessment.md) referencing the Report hash, apart from the
   CLI's facts and the human's Reading Verdict.
5. **Plan.** `galley deliver READY --plan --json` per Ready Artifact, gathering a finite set that
   names the exact device, destination, artifact and action.
6. **Deliver.** One approval covers the displayed set; then perform each plan as its own
   `galley deliver` invocation and read each Delivery Record.

It is one pass that stops at the plans for approval — the guide states the four disciplines that
keep it so. After a book reaches the device, the reader follows
[the device-read protocol](resources/device-read.md).

## The ordinary path

1. `inspect` with `--evidence-dir` when a repair looks likely, otherwise go straight to
   `prepare`. Preparation always writes its own evidence directory.
2. Read the Report and derive the worklist from it: every observation whose `fired` is `null` and
   whose `applicability` is not `false`, plus every engaged preparation interlock. The same Report
   always yields the same list, so it is read off rather than chosen.
3. Settle the entries whose `evidence` is `flaggable`, from the previews in the evidence
   directory. A `device-judged` entry stays outstanding under the reader's name.
4. Record those judgements and one Predicted Verdict in an assessment referencing the Report's
   SHA-256, then hand the artifact and what is still outstanding to the human. Where the document
   leans on figures, `preparation.images.reduction` says how far they shrank to fit the panel, and
   the reader gets [a plain heads-up](resources/assessment.md) about it before they start.

[The worklist and the assessment record](resources/assessment.md) carry the derivation and the
decided fields. A completed run with an empty worklist is finished — say so and stop.

## When the work needs a cover

Cover Artwork is creative editorial work, not a CLI-generated decoration. During Assisted
Preparation, normally delegate its complete creative loop to a focused cover subagent. If
delegation is unavailable, take that complete role yourself. Whoever owns it uses
[the cover guide](resources/cover-artwork.md) to interpret the work, author and preview one SVG, and
judge the rendered result. A cover for another profile is a new composition under that profile's
direction, not a recolour preset.

## When the artifact goes to Kindle for iOS

Galley publishes the EPUB as a Ready Artifact in the Workspace and stops. Do not ask for an iCloud
Drive folder, copy the EPUB into one or upload it to Kindle. Read
[the Kindle user handoff guide](resources/kindle-ios-handoff.md), report the Ready Artifact's exact
local path, and tell the person to upload or share that file through their preferred Send to Kindle
route.

## When the pictures are still on the web

A Markdown source saved from a website references its images where the website put them, and
`prepare` reads local bytes for a Markdown source. So the build refuses at
`image-processing-failure` with every reference `unsupported-location`, and that pair is routine
rather than a judgement call: run `galley localise` once, read what it retrieved, and re-prepare
from the Repair Set it wrote. One approval covers the document, and each picture is not a separate
question. [The localisation guide](resources/localisation.md) has the sequence and every boundary
it can refuse at.

Preparation stays fetch-free deliberately. A `prepare` that retrieved would make the same file on
disk build a different book tomorrow, and say nothing about it.

## When to repair

Two Report facts together mean footnotes are hiding in the document: link stripping reports its
interlock **engaged**, and `extraction.footnote_recovery` reports `not-recognised` or `skipped`.
That pair is the trigger. Other repairs exist — a heading level extraction demoted, for
instance — and the same procedure carries them.

The repair procedure, in five steps:

1. **Inspect and keep the evidence.** The Canonical Document and Preservation Baseline are what
   a repair works on and what it is later measured against.
2. **Match the shape against [Repair Conventions](resources/repair-conventions.yaml).** If an
   entry names it, the entry states its completeness boundary, ambiguity response, target and
   retained evidence. If none does, the repair is still yours to write — a Bespoke Repair needs
   no convention.
3. **Rewrite the Canonical Document's Pandoc AST**, changing nothing else in the envelope. Follow
   the convention's target native document structure rather than inventing a representation.
   Repair the Canonical Document, never a generated EPUB: by the time a book exists preparation
   decisions are already made and editing it hides the damage instead of fixing it.
4. **Declare exactly what the repair consumes** through `--expected-missing-tokens`, then
5. **Resubmit** with all three Repair Inputs. Galley proves they belong to this source before it
   uses them, and refuses undeclared text loss.

[The worked repair](resources/worked-repair.md) walks one all the way through, on both carriers.

## Where a repair stays

A Bespoke Repair is a fact about one document or one source, and it belongs to you permanently.
There is no path into the CLI, however often the source recurs — capabilities enter by being
general, true of a format or a Device Profile, and one document is enough evidence when the fact
is structural.

So recurrence is a prompt, not a promotion. Several *unrelated* sources needing the same hand-fix
means the general layer is probably missing something; investigate it, and let whatever general
thing you find enter on its own generality. Record what you learn about a source in
`repair-conventions.yaml`, where knowledge grows without these instructions growing.

## What stays out of your hands

Galley reports facts and refuses; it does not recommend, score or grade, and neither should you
on its behalf. Four artifacts stand side by side and each is written once: the CLI's Report, your
assessment against its hash, the Delivery Record, and the human's reading record. They can
disagree — a clean build, your concern, a confirmed Delivery and a reader who finds it fine are
all true at once — and each stays as its author left it. The Reading Verdict is the human's,
after a real device read; a mechanically successful build has never been evidence that a book
reads well.
