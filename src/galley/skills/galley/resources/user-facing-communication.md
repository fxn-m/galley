# Talking to the reader

Galley keeps two surfaces deliberately different. Its technical surface is exact: commands,
Reports, evidence, assessments, hashes and formal workflow states. Its conversational surface is
plain: what is happening, what matters to the reading experience, and whether the person needs to
decide or do anything.

## Give useful updates, not a narrated pipeline

Update the person at meaningful transitions:

- setup is needed or a target must be chosen;
- a finding changes the work or needs their judgement;
- a long-running conversion reaches a genuinely useful milestone; or
- the file is ready, refused or blocked.

Combine adjacent internal stages into one update. Loading a resource, invoking a command, spawning
a cover subagent, retaining evidence, changing an internal classification and running another
mechanical check are work to perform, not separate events the reader must absorb.

Each routine update should lead with the outcome in one or two sentences. Name the concrete issue
and its consequence. Add technical detail only when it explains a failure, supports a decision or
the person asks for it.

## Translate Galley's vocabulary

Formal terms remain valid inside the workflow, but they are not conversational labels. Translate
them into the reader's language:

| Internal fact | Say to the reader |
|---|---|
| Workspace configuration is missing | “Galley needs setting up first.” |
| Routine Assisted Preparation | “The article looks straightforward.” |
| Repairing Assisted Preparation | “I found a broken embed and can repair it without changing your original.” |
| Localisation | “I’m downloading the article’s images.” |
| Canonical Document or Preservation Baseline | Usually say nothing; they are retained evidence. |
| Cover subagent accepted the rendered SVG | “The cover is ready.” |
| EPUBCheck and preservation checks completed | “It passed Galley’s checks.” |
| Ready Artifact | “Your Kindle-ready file” or “your X4-ready file.” |

Terms such as refusal boundary, interlock, profile id, profile version, deterministic renderer,
immutable artifact, declared tokens and report hash stay in technical evidence unless one is the
reason the person must act.

Prefer:

> I found ten images and one broken video embed. I can repair the embed without changing your
> original file, then continue.

over a report-style account of classification changes, carriers, baselines and proof steps.

## Finish with the file and the next action

For a successful conversion, lead with the clickable file path. Then state the next action and at
most the reading caveats that matter, such as a heavily reduced diagram. “It passed Galley's
checks” is enough for routine success.

Offer the evidence path as **Technical report** after the primary handoff. File size, SHA-256,
profile identifiers and versions, individual checker counts and repair declarations stay out of
the primary response unless requested or needed to distinguish artifacts.

For a refusal or blocker, explain the concrete problem and the next decision in plain language;
link the technical report when one exists. The Report remains complete even when the conversation
is brief.
