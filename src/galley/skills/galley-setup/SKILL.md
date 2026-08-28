---
name: galley-setup
description: Author and validate a Galley Workspace Configuration through a short first-run conversation. Use when Galley reports missing or invalid Workspace Configuration, when setting Galley up for the first time, or when changing the Workspace, its Inboxes, or the CrossPoint host and destination.
---

# Galley setup

Galley's CLI reads and validates Workspace Configuration and never writes it. Authoring the
visible `galley.toml` is this skill's whole job: ask six things, show one summary, take one
confirmation, write the file with ordinary file tools, then hand the result to the read-only
validator.

Detail lives in two bounded resources:
[the configuration contract](resources/workspace-config.md) for the strict schema, the annotated
template and every refusal, and [reconfiguration](resources/reconfiguration.md) for editing a
Workspace that already exists. Once setup validates, the reading workflow belongs to the `galley`
skill.

## The six questions

Ask all six in one message, each with its default shown, so a user who is content with every
default can answer "all defaults" and be finished in one response.

| Subject | Ask | Default |
|---|---|---|
| `workspace` | Where should the Galley Workspace live? | `~/Documents/Galley` |
| `inboxes` | Which directories hold the documents you want to read? | one Inbox at `inbox` inside the Workspace |
| `recursion` | For each Inbox, descend into subdirectories? | `false` |
| `host` | What is the X4's CrossPoint host? | `crosspoint.local` |
| `destination` | Which folder on the device receives books? | `/` |
| `probe` | May I ask the device for its status once, read-only? | no probe |

Those six are the whole question set. Everything else Galley needs is either fixed release data
or a Galley-owned path, so asking about it would offer a choice that does not exist.

## Naming the Inboxes

Propose each Inbox's name from its directory basename, lowercased, with spaces and underscores
becoming hyphens — `~/Documents/Reading Queue` proposes `reading-queue`. The user can rename any
of them; the name is how coverage and attribution are reported, so it should be one they
recognise.

Two situations go back to the user rather than being settled quietly, because both change what
gets read:

- **Two Inboxes proposing the same name.** State both paths and ask which name each takes. A
  generated suffix would resolve it invisibly and leave a name nobody chose.
- **A path that cannot serve as an Inbox** — absent, a regular file, or unreadable. Say what you
  found at that path and ask for a decision, and remember that configured order decides which
  Inbox owns a source two of them can see.

## One summary, one confirmation

Show the complete proposed state in one message: the Workspace path, every Inbox with its name,
the path as it will be written and its recursion, the host and destination, the exact directories
you will create, and the complete TOML you are about to write. For a Workspace that already has a
configuration, show a diff of the file instead.

Then take one confirmation covering all of it, and write only after that.

## What setup may create

With ordinary file tools, and only inside the Workspace:

- the Galley Workspace directory itself;
- the Galley-owned `work/`, `ready/`, `ready/evidence/` and `delivery/` locations beneath it;
- the default Inbox directory, and only when it sits inside the Workspace.

An Inbox outside the Workspace is the user's own directory. It must already be a readable
directory before it is configured — confirm that, then record it exactly as it is. Creating,
moving or tidying someone's reading directory is outside this skill's authority, and so is
deleting anything: `work/`, `ready/`, its Reports and evidence, and `delivery/` all survive every
run of this skill.

## Writing the TOML

Author the file directly. `version = 1` comes first, then one `[[inbox]]` table per Inbox in the
order the user gave them, then `[x4-crosspoint]` for a host or destination the user actually
chose. Leaving a device value out is meaningful: the validator reports it as `default` rather than
`configured`, which keeps the file a record of decisions instead of a copy of Galley's defaults.

## Validating, and the optional probe

Finish by invoking the read-only validator:

```
galley config validate --workspace WORKSPACE --json
```

Exit `0` means the configuration reads and every path it names can serve its role. Exit `3` means
it refused: read `refusal.boundary` and `refusal.summary`, correct the file, and validate again.
[The configuration contract](resources/workspace-config.md) lists what each boundary means.

Then, only with the permission question 6 asked for:

```
galley device status --workspace WORKSPACE --json
```

This reads the device and writes nothing. An X4 that is asleep, in another mode, or off the
network refuses at `device-unavailable` — that is a fact about the device at that moment and says
nothing about the configuration, so report it and leave a validated setup complete.
