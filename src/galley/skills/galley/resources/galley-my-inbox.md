# "Galley my inbox", end to end

One request carries a Workspace from validated configuration through Inbox Check and preparation
to a finite set of reviewed Delivery Plans. The CLI owns every deterministic fact and refusal
along the way; you orchestrate the phases, judge what it leaves outstanding, and hold the one
human approval Delivery needs. It is a single pass over the Inbox, not a watch.

## 1. Validate configuration

```
galley config validate --json
```

Exit `0` means the Workspace reads. A refusal at a configuration boundary —
`workspace-configuration-missing`, `invalid-workspace-configuration`,
`unknown-configuration-key`, `unsupported-configuration-version`, `duplicate-inbox-name`,
`inbox-unavailable` or `workspace-location-unusable` — means configuration is what stopped the
run. Hand that user to the `galley-setup` skill, which owns the question set and authors the
file, and resume here once it validates. Authoring `galley.toml` from this skill would put
configuration the user has never seen behind everything Galley later reports.

## 2. Run one Inbox Check

```
galley inbox check --json
```

Read the `galley/inbox-check/1` document. Per-Inbox coverage is `checked` or `unavailable`. An
unavailable Inbox leaves its candidates **unknown**, and unknown is reported as unknown: a
completed check over a Workspace with one unreadable Inbox is not a claim that the reachable
candidates are all there are. Treat an unavailable Inbox as coverage you did not get, and say so
to the user, rather than as an Inbox that was empty.

Every candidate carries a `state`, a resolved path, a SHA-256 content hash, and the Inbox names
it matched. The display path is for reading; identity is the resolved path and the hash.

## 3. Prepare the routine candidates

Prepare every candidate whose `state` is `new` or `changed` and whose identity is unambiguous,
without stopping to confirm each one:

```
galley prepare RESOLVED_PATH --profile x4-crosspoint --ready \
  --expected-source-hash HASH --json
```

`--expected-source-hash` is the hash Inbox Check observed. Galley re-checks it before and after
reading the source, so a file edited mid-run refuses, retains its attempt evidence, and publishes
no Ready Artifact — the routine path stays safe without a per-file prompt. `already-ready`
candidates are already published; leave them for the Delivery phase. Inbox preparation never
authors Cover Artwork, regardless of the Workspace setting: each candidate receives a Default
Cover or keeps a source `cover-image`.

Stop **only the affected candidate**, with its evidence kept, when any of these appears — the
other candidates keep going:

- **Identity is ambiguous.** A candidate whose display name collides with another's, or whose
  membership across overlapping Inboxes changes what "this document" means, is a question for the
  user before a build, not a guess.
- **A repair decision is consequential.** The link-stripping interlock is engaged and footnote
  recovery reports `not-recognised` or `skipped`, or another Canonical Document correction is in
  play. That is a Bespoke Repair — see [the worked repair](worked-repair.md) — and its choices are
  yours to make deliberately, not to batch.
- **The CLI refuses.** A structured refusal names its boundary and stage and keeps the facts
  gathered before it stopped. Report it against that one candidate and move on.

One refusal is not a stop. `image-processing-failure` whose references are all `http` or `https`
`unsupported-location` is a saved web article whose pictures are still on the web: run
[localisation](localisation.md) for that candidate, then prepare it again from the Repair Set,
inside the same unattended pass. Say what was retrieved and from where when you report the run.

## 4. Settle outstanding items and say material caveats

The CLI's Report is the deterministic record. Read compact Report facts. Settle each observation
whose `fired` is `null` from the previews beside it, and say material caveats — including a
figure-reduction heads-up when the document leans on pictures. Leave an Agent Assessment and
Predicted Verdict for a later eval or device-read. Do not write a technical report, helper
script, or extra note on a routine run. The human's Reading Verdict is filled in only after a
device read.

## 5. Gather the Delivery Plans

Every Ready Artifact — freshly published or already ready — is a candidate for one Delivery Plan.
Plan each one against the device without uploading:

```
galley deliver READY_ARTIFACT --plan --json
```

A plan reads device status and the destination listing and records one exact action: `upload new`,
`already delivered`, an overwrite collision, or a refused collision. Collect the finite set and
present it so the user reads plainly, for each plan, **which artifact goes to which device and
destination and what will happen there**. Then wait.

## 6. Deliver, one plan at a time, after one approval

One human approval may cover the whole displayed set. With it, perform each plan as its own
invocation:

```
galley deliver READY_ARTIFACT --json
```

Each Delivery persists an immutable `galley/delivery-record/2`. Read every record: a `delivered`
outcome is confirmed by a fresh destination listing, `already-delivered` uploaded nothing, and
`unconfirmed` at exit `5` means the bytes may or may not have landed — retry from a fresh plan,
which re-runs the preflight and reports `already-delivered` if the first upload in fact completed.

## The four disciplines this phase keeps

These are what "Galley my inbox" means for Delivery, and they are the point of doing it here
rather than in a shell loop:

- **One artifact per invocation.** Each Delivery is its own `deliver` call with its own record;
  uploads are never folded into a single batched shell command.
- **Confirmation comes from the record.** Success is read from the Delivery Record's own
  post-upload listing, never inferred from a command that merely produced no error.
- **A single pass.** Inbox Check and Delivery run once for the request and then stop; nothing
  watches the Inbox or the device continuously.
- **Approval precedes upload.** The plans are presented and the human approves before any
  `deliver` writes to the device; a plan alone uploads nothing.

After a book reaches the device, the reader follows [the device-read protocol](device-read.md).
