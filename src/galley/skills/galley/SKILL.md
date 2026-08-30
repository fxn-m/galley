---
name: galley
description: Prepare documents for constrained reading environments with the Galley CLI. Use when inspecting, preparing or auditing Markdown or an Article-Like Page for a Device Profile, handing off a Kindle-ready EPUB, delivering a Ready Artifact to X4, reading a Galley Report, or repairing a misread document before resubmission.
---

# Galley

Galley turns supported reading material into EPUBs that work on a constrained reading device.
Three layers do three jobs, and this skill is the middle one:

- **The CLI** owns deterministic, general behaviour and every Report Fact and refusal.
- **You** orchestrate, judge what the CLI leaves outstanding, and write Bespoke Repairs.
- **A human** records the Reading Verdict, after reading the book on the device.

Detail lives in bounded resources rather than in this file:
[keeping the conversation plain](resources/user-facing-communication.md),
[the command contract](resources/cli-contract.md),
[reading a Report](resources/report-fields.md),
[leading an Assisted Preparation](resources/assisted-preparation.md),
[Repair Conventions](resources/repair-conventions.yaml),
[a complete worked repair](resources/worked-repair.md),
[localising a document's remote images](resources/localisation.md),
[authoring profile-directed Cover Artwork](resources/cover-artwork.md),
[handing a Ready Artifact to a Kindle user](resources/kindle-ios-handoff.md),
[continuing an X4 preparation into separately authorised Delivery](resources/x4-delivery.md),
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

## Keep the conversation plain

Read [the user-facing communication contract](resources/user-facing-communication.md) before the
first update. Galley's formal vocabulary belongs in commands, Reports and retained evidence. Tell
the reader what is happening in ordinary language, at meaningful transitions, with technical
details available rather than foregrounded.

## Establish Workspace readiness before conversion work

For every natural-language request to prepare one source as a Ready Artifact, begin with
`galley config validate --json`. This gate comes before `profiles list`, reading the source,
`inspect`, profile-directed cover work, Localisation, repair or `prepare`. Exit `0` means the
Workspace is ready. A refusal at `workspace-configuration-missing`,
`unreadable-workspace-configuration`, `invalid-workspace-configuration`,
`unknown-configuration-key`, `unsupported-configuration-version`, `duplicate-inbox-name`,
`inbox-unavailable` or `workspace-location-unusable` hands the user immediately to the
`galley-setup` skill.

Pause the conversion at that boundary and resume the same request only after setup's final
validator returns exit `0`. Setup answers make the Workspace usable but leave the Device Profile
unselected; profile confirmation follows validation.

## Confirm the Device Profile before conversion work

For every one-source conversion, run `galley profiles list --json` and read the command contract.
The shipped reader-facing labels are **Kindle for iOS** for `kindle-ios-personal-documents` and
**Xteink X4** for `x4-crosspoint`. When the request explicitly names Kindle or X4, state that
concise choice and proceed without another question. When it names no target, show the concise
choices and ask the user to choose before profile-specific work. Keep the profile id in commands
and Reports; the Kindle label carries no observed iPhone model.

Only the current request selects the profile. Workspace configuration, setup answers, available
hardware, prior runs, source content and list order provide no selection. When setup interrupts a
conversion, retain a choice already established by that request; otherwise ask before resuming.

## Assisted Preparation

When the user chooses one source and wants the complete agent-guided journey to a Ready Artifact,
follow [the Assisted Preparation contract](resources/assisted-preparation.md).
It begins with Workspace validation, then profile confirmation and inspection, and gives the user
a concise account of meaningful findings, decisions and the finished file while the exact
classification, repair, cover, Localisation and preparation evidence stays retained.
Preparation finishes when the immutable Ready Artifact is published. Kindle submission remains
user-controlled; X4 Delivery is a separate planned and authorised continuation.

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
4. **Settle.** Read compact Report facts, settle flaggable worklist items, and say material
   caveats. Leave an Agent Assessment for a later eval or device-read.
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
2. Read compact Report facts and derive the worklist from them: every observation whose `fired` is
   `null` and whose `applicability` is not `false`, plus every engaged preparation interlock. The
   same Report always yields the same list, so it is read off rather than chosen.
3. Settle the entries whose `evidence` is `flaggable`, from the previews in the evidence
   directory. A `device-judged` entry stays outstanding under the reader's name. Say material
   caveats, including a figure-reduction heads-up when `preparation.images.reduction` shows the
   document leans on pictures.
4. Hand the artifact and what is still outstanding to the human. Write an
   [assessment](resources/assessment.md) only when a later eval or device-read needs one.
   Do not write a technical report, helper script, or extra note on a routine run.

A completed run with an empty worklist is finished — say so and stop.

## When the work needs a cover

Read `cover_artwork` from the successful `config validate`. Silence follows that setting. An
explicit “make a nice cover for this one” or “plain cover only” overrides it for this request
only. A source `cover-image` stands. Cover Artwork runs only when Galley would otherwise publish
a Default Cover and the setting or override asks for custom covers. Inbox preparation never
authors Cover Artwork.

When Cover Artwork does run, it is creative editorial work, not a CLI-generated decoration.
During Assisted Preparation, normally delegate its complete creative loop to a focused cover
subagent. If delegation is unavailable, take that complete role yourself. Whoever owns it uses
[the cover guide](resources/cover-artwork.md) to interpret the work, author and preview one SVG, and
judge the rendered result. A cover for another profile is a new composition under that profile's
direction, not a recolour preset.

## When the artifact goes to Kindle for iOS

Galley publishes the EPUB as a Ready Artifact in the Workspace and stops. Do not ask for an iCloud
Drive folder, copy the EPUB into one or upload it to Kindle. Read
[the Kindle user handoff guide](resources/kindle-ios-handoff.md), link the exact published file, and
give its one user-controlled Send to Kindle instruction.

## When the artifact goes to X4

After successful one-source X4 preparation, follow
[the X4 Delivery continuation](resources/x4-delivery.md). Read the plan silently, ask only about
the exact consequential action it supports, and treat the answer as authority for that action
alone. Direct CLI use and Inbox batching keep their existing authorization contracts.

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
on its behalf. The CLI's Report, the Delivery Record, and the human's reading record each stand
alone. An assessment against a Report hash is written when a later eval or device-read needs one,
not on the routine conversion path. Those artifacts can disagree — a clean build, a later concern,
a confirmed Delivery and a reader who finds it fine are all true at once — and each stays as its
author left it. The Reading Verdict is the human's, after a real device read; a mechanically
successful build has never been evidence that a book reads well.
