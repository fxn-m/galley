# Leading an Assisted Preparation

Assisted Preparation is the complete agent-guided production of one Ready Artifact from one chosen
source. It uses Galley's existing public commands and keeps the inspection, any Bespoke Repair,
Cover Artwork, Localisation and one preparation in one visible journey.

Before the first update, read [the user-facing communication contract](user-facing-communication.md).
The workflow terms below direct internal work; translate them into concrete, ordinary language for
the reader.

## Validate Workspace readiness first

Begin every Assisted Preparation with `galley config validate --json`. Run this before
`galley profiles list`, reading the source, inspection, Cover Artwork, Localisation, repair or
preparation. A configuration refusal hands the request immediately to `galley-setup`; pause source
work while setup establishes and validates the Workspace. Resume this same request only after
setup's final `galley config validate --json` completes.

Read `customisation.instructions` from that validation and follow
[the customisation guide](customisation.md). Carry applicable preferences through preparation,
cover authorship and the final handoff; an explicit instruction for this document takes precedence.

## Confirm the Device Profile first

Before profile-specific work, run `galley profiles list --json`. The shipped labels are **Kindle
for iOS** for `kindle-ios-personal-documents` and **Xteink X4** for `x4-crosspoint`. An explicit
Kindle or X4 request establishes that profile: state the concise label and continue. With no named
target, present the concise choices and wait for the user's selection. Keep ids and observed-device
provenance in commands and Reports.

The current request is the only selection authority. Workspace configuration, setup answers,
available hardware, prior runs, source content and list order do not choose. If setup interrupts a
pending conversion, resume with the target already established by that request; otherwise ask.

## Inspect and classify first

Begin with
`galley inspect SOURCE --profile PROFILE --evidence-dir INSPECTION.galley --json`, retaining its
Canonical Document, Preservation Baseline and Report. Read the chosen source and that inspection
evidence before starting any repair, Cover Artwork, Localisation or final preparation, then tell the
workflow which internal classification the evidence supports:

- **Routine Assisted Preparation** when inspection finds no need for a Bespoke Repair. Cover
  Artwork or Localisation may still be required.
- **Repairing Assisted Preparation** when restoring meaning or structure requires a Bespoke Repair.

## Reclassify when evidence changes

Classification follows evidence rather than locking the journey onto its first path. If later
evidence reveals a Bespoke Repair in what began as Routine Assisted Preparation, change the
internal classification to Repairing Assisted Preparation. Tell the user the specific finding and
what it means in plain language, without naming the classification or narrating proof machinery.

## Decide whether to repair or ask

Proceed autonomously with a Bespoke Repair only when all three hold: the repair is unambiguous,
reversible and retained outside the original source. Preserve the inspection evidence and the
original source while making one coherent repair pass.

Ask the user before changing Central Content, choosing between plausible authorship or meaning, or
making a material editorial interpretation. Keep the source unchanged while that choice is open.

## Follow the Cover Artwork setting

Read `cover_artwork` from the successful `config validate`. `value` is whether custom covers are
on; `source` is `configured` or `default`. Silence follows that setting.

- Setting off, or omitted: prepare once. Galley publishes a Default Cover or keeps a source
  `cover-image`. Do not start a cover agent.
- Setting on, and no source `cover-image`: author Cover Artwork by the existing creative workflow,
  attach it, then prepare once.
- A source `cover-image` stands even when the setting is on.
- “Make a nice cover for this one” or “plain cover only” overrides the setting for this request
  only.

Then ask “Send it to X4?” about that exact Ready Artifact. Artwork and send are never one question.
A later cover change publishes a new Ready Artifact; ask “Send it to X4?” about that new file.
Republishing the same source and hash at the existing Ready path refuses at `output-exists`.

## Delegate Cover Artwork when possible

When this request calls for Cover Artwork, normally delegate it to a focused cover subagent and give it
[the cover guide](cover-artwork.md), the source, the selected profile's direction, applicable saved
cover preferences and the relevant evidence. It owns interpretation, identity-cue research,
SVG creation, rendering, visual judgment
and revision as one task. It does not compare against recent Galley covers.

When the subagent accepts its SVG, the main agent attaches it and reads only the automated Report
evidence that Galley rasterised, referenced and packaged the cover. The main agent does not perform
a second creative or visual review. When delegation is unavailable, the main agent assumes the
complete cover role, including interpretation, research, creation, rendering, visual judgment and
revision under the same guide.

## Work after classification

Continue from the retained inspection evidence through the work the classified journey requires:

- Batch coherent repairs discovered by the initial inspection and make one coherent repair pass,
  rather than preparing repeatedly to discover source structure.
- Parallelise only independent work whose inputs cannot be changed by another branch. Keep
  dependent repair, cover, Localisation and preparation work in evidence order.
- Have the active cover author preview the SVG before packaging. A delegated cover returns only
  after its owner has rendered, judged and revised it; the main agent does not repeat that review.
- Run final preparation with `--ready` once its inputs are settled, then read compact Report facts
  for the outcome, worklist, cover rasterisation, reference and packaging evidence. Raster and font
  facts for Cover Artwork are checked on that one prepare. The completed Report's `artifact.path`
  is the path handed to the user.

If later failure is unambiguous, fix it and continue from the new evidence. If it exposes ambiguity
or a Central Content judgment, stop and ask the user rather than entering repeated blind retries.

Routine conversion is that named work: inspect, localise, repair when needed, prepare once, and
continue into Delivery. Read compact Report facts rather than the whole JSON dump. Settle flaggable
worklist items and say material caveats, including a figure-reduction heads-up when the document
leans on pictures. Attach a cover SVG without rewriting title or author metadata Galley will
reassert at packaging. Write an Agent Assessment only when a later eval or device-read needs one.
Do not write a technical report, helper script, or extra note on a routine run.

## Hand off the published artifact

One completed Report publishes one immutable Ready Artifact and ends Assisted Preparation. Lead
routine success with “It passed Galley's checks.” Render the exact artifact basename as clickable
text whose target is the Report's absolute `artifact.path`; do not print that raw path separately.
Keep hashes, profile ids, evidence directories, report filenames, formal workflow labels and a
Technical report link out of the routine handoff. Link the Technical report for a material caveat,
refusal or ambiguity when it helps, and whenever the user asks for retained details.

For Kindle, follow [the user-controlled handoff](kindle-ios-handoff.md). For X4, the separately
authorised [Delivery continuation](x4-delivery.md) may begin after this preparation boundary. A
one-off request ends after its useful handoff; plural or clearly unfinished work continues with the
next item that is already in scope.

## Keep the workflow boundary

Assisted Preparation remains guidance over Galley's existing public interfaces.
It introduces no new public command, daemon, state machine, Assisted Preparation Record, timer,
telemetry, target, score, retry counter, dashboard or service-level objective. Existing CLI Report
timing remains compatible, but this workflow does not read it as a success measure.
