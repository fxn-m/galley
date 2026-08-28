# Leading an Assisted Preparation

Assisted Preparation is the complete agent-guided production of one Ready Artifact from one chosen
source. It uses Galley's existing public commands and keeps the inspection, any Bespoke Repair,
Cover Artwork, Localisation, preparation and assessment in one visible journey.

Before the first update, read [the user-facing communication contract](user-facing-communication.md).
The workflow terms below direct internal work; translate them into concrete, ordinary language for
the reader.

## Validate Workspace readiness first

Begin every Assisted Preparation with `galley config validate --json`. Run this before
`galley profiles list`, reading the source, inspection, Cover Artwork, Localisation, repair or
preparation. A configuration refusal hands the request immediately to `galley-setup`; pause source
work while setup establishes and validates the Workspace. Resume this same request only after
setup's final `galley config validate --json` completes.

## Confirm the Device Profile first

Before inspection or any other profile-specific work, run `galley profiles list --json`, present
concise reader-facing choices, and ask the user to confirm the target for this artifact. The shipped
confirmation labels are **Kindle for iOS** for `kindle-ios-personal-documents` and **Xteink X4** for
`x4-crosspoint`. The `device` and observed-software fields are profile provenance rather than part
of those labels: say **Kindle for iOS**, without the observed iPhone model. Keep the profile id for
commands and Reports. A profile named in the request may be proposed, but it is not active until
the user confirms it.

Do not infer this choice from Workspace configuration, setup answers, available hardware, prior
runs, source content or list order. If setup interrupts a pending conversion, resume with a target
that was already confirmed for that request; otherwise ask before continuing.

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

## Delegate Cover Artwork when possible

Normally delegate Cover Artwork to a focused cover subagent and give it
[the cover guide](cover-artwork.md), the source, the selected profile's direction and the relevant
evidence. It owns interpretation, identity-cue research, SVG creation, rendering, visual judgment
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
  for the outcome, worklist, cover rasterisation, reference and packaging evidence. The completed
  Report's `artifact.path` is the path handed to the user.

If later failure is unambiguous, fix it and continue from the new evidence. If it exposes ambiguity
or a Central Content judgment, stop and ask the user rather than entering repeated blind retries.

## Keep the workflow boundary

Assisted Preparation remains guidance over Galley's existing public interfaces.
It introduces no new public command, daemon, state machine, Assisted Preparation Record, timer,
telemetry, target, score, retry counter, dashboard or service-level objective. Existing CLI Report
timing remains compatible, but this workflow does not read it as a success measure.
