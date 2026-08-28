# Reconfiguring an existing Workspace

A second run of setup edits a file the user already owns, so it is an edit rather than a rewrite.
Read the existing `galley.toml` first and work from what is there.

## What survives an edit

- **Comments and blank lines**, including ones the user wrote themselves. Edit the lines that
  change and leave the rest of the file byte-for-byte alone; regenerating the file from the
  template discards their annotations.
- **Table ordering.** `[[inbox]]` order decides which Inbox owns a source that two of them can
  see, so reordering silently changes attribution. Add a new Inbox at the position the user asks
  for, and say what that position means for overlap.
- **Every value the user did not confirm.** A reconfiguration changes the values under discussion
  and nothing else.
- **Everything Galley owns.** `work/`, `ready/`, its Ready Artifacts, Reports and evidence
  bundles, and `delivery/` with its Delivery Records are all immutable history. Setup adds
  directories; removing one is a decision only the user makes, outside this skill.

## The shape of the conversation

1. Read the current file and report what it says now — Workspace, each Inbox with its recursion,
   and any configured X4 host and destination. The presence or absence of `[x4-crosspoint]` is not
   evidence of which Device Profile the user wants for a conversion.
2. Ask only about what the user came to change. The six subjects in the first-run table are the
   complete decision set, not six mandatory prompts; a user changing one Inbox path answers one
   question. Follow the entry skill's native-question rule and ordinary-chat fallback.
3. Show a **diff** of the file rather than a summary of the new state, so the user sees exactly
   which lines move.
4. Take one confirmation, apply the edit, and validate.

## Moving the Workspace

Changing where the Workspace lives changes where `work/`, `ready/` and `delivery/` are looked for,
and Galley moves nothing. Say that plainly, and let the user decide whether to move the existing
directories across or start the new Workspace empty. Either is valid; guessing is not.

## Removing an Inbox

Deleting an `[[inbox]]` table stops Galley reading that directory. It leaves the directory and
every artifact already prepared from it exactly as they are — an Inbox is a read-only source
location, so removing it from the file is the whole of the change.

## Finishing

Validate as first-run setup does, and report the boundary if it refuses:

```
galley config validate --workspace WORKSPACE --json
```

A device probe stays optional at reconfiguration too, and a device that will not answer leaves a
valid configuration valid.
