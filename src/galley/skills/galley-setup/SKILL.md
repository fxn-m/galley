---
name: galley-setup
description: Bootstrap Galley's pinned external tools and author or repair its Workspace Configuration. Use for first-run setup, dependency failures, or changes to the Workspace, Inboxes, or CrossPoint connection.
---

# Galley setup

A complete setup leaves Galley's four pinned external commands runnable and its visible
`galley.toml` valid. Galley's CLI reads and validates Workspace Configuration and never writes it,
so agent skills author the file. This skill owns dependency bootstrap and Workspace setup.

For a preference-only request, such as remembering a destination or cover style, use
[the customisation guide](../galley/resources/customisation.md) directly. Read and validate the
existing settings, then make the authorised edit without a dependency inventory or setup interview.
An explicit request to save a preference needs no second confirmation.

Detail lives in three bounded resources:
[dependency bootstrap](resources/dependencies.md) for the exact release requirements, probes,
installation sources and approval boundary,
[the configuration contract](resources/workspace-config.md) for the strict schema, the annotated
template and every refusal, and [reconfiguration](resources/reconfiguration.md) for editing a
Workspace that already exists. Once setup validates, the reading workflow belongs to the `galley`
skill.

## Keep setup plain

The inventory and configuration remain exact, but the person needs outcomes and choices rather
than a narrated setup pipeline. Say **Galley needs setting up first**, ask the applicable questions,
and move directly from their answers to the complete approval summary. Loading instructions,
probing tools, resolving paths and preparing that summary need no separate progress announcement.

Use ordinary names in conversation: **required tools**, **Galley folder**, **reading folder** and
**settings**. Reserve dependency bootstrap, Workspace Configuration, Device Profile, refusal
boundary and validator terminology for the retained technical work or for diagnosing a failure.
After approval and successful validation, say simply that setup is complete and resume the original
request.

## Start with a read-only dependency inventory

Read [dependency bootstrap](resources/dependencies.md), detect the platform and architecture, and
run all four version probes before asking the configuration questions. A ready command needs no
discussion. For anything absent, unusable or at another version, work out the exact installation
route and retain it for the summary.

Dependency releases are fixed Galley release data, not user choices. Run the approved installation
commands yourself; a command list is the plan the user approves, not homework to hand back to them.
If an installer prerequisite such as npm or Java is absent, include that prerequisite in the same
plan rather than asking the user to obtain it first.

## Scope setup to the user's reading targets

Before offering configuration defaults, ask which readers the user expects this Workspace to
support: **Kindle for iOS**, **Xteink X4**, or **both**. This answer scopes the setup conversation;
it is not written to `galley.toml`, does not establish a default Device Profile, and leaves the
profile for every later conversion unselected.

Ask about the CrossPoint host, destination and optional probe only when the answer includes X4. A
Kindle-only setup has no X4 connection decisions and writes no `[x4-crosspoint]` table. The main
Galley skill separately confirms the Device Profile for every individual conversion.

## One configuration fast path, then only unresolved questions

After the inventory, ask one choice between **All recommended defaults** and **Customise**. If the
user takes the defaults, accept every default in the table below and ask no more configuration
questions that apply to the selected readers. If they customise, ask which applicable defaults
should differ and then ask only for those values, in batches of at most three questions.

Use a native structured-question tool when the current harness exposes one in the current mode,
and obey its live schema. Do not change modes merely to obtain a picker; when no picker is
available, ask the same compact questions in ordinary chat. For a native picker, use short
headers, put the recommended answer first, explain each option's consequence in one sentence, and
keep choices mutually exclusive unless the tool explicitly supports multi-select. Do not add an
**Other** option when the host supplies one. Paths, names and hostnames may use the host's free-text
route or ordinary chat.

| Subject | Ask | Default |
|---|---|---|
| `workspace` | Where should the Galley Workspace live? | `~/Documents/Galley` |
| `inboxes` | Which directories hold the documents you want to read? | one Inbox at `inbox` inside the Workspace |
| `recursion` | For each Inbox, descend into subdirectories? | `false` |
| `covers` | Do you want custom covers? | no |
| `host` | What is the X4's CrossPoint host? | `crosspoint.local` |
| `destination` | Which folder on the device receives books? | `/` |
| `probe` | May I ask the device for its status once, read-only? | no probe |

Those seven subjects are the first-run setup decision set, not a requirement to produce seven
prompts. The final three apply only when setup includes X4. Reader scope is onboarding context, not
another configuration key. Additional reading preferences belong in optional customisation when
the user asks to remember them, separately from the first-run questions.

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

Show the complete proposed state in one concise message:

- when every dependency is ready, one line saying all required tools are ready;
- every proposed dependency change, including the exact command or immutable download, digest,
  destination and any PATH or shell-profile edit;
- the selected readers, without explaining internal persistence unless the user asks;
- the Workspace path, every Inbox with its name, written path and recursion, whether custom
  covers are on, any applicable X4 host and destination, and the directories and settings you
  will create.

Show the complete TOML under **Technical details** only for customised first-run settings or when
the user asks to see it. Recommended defaults are fully described by the concise proposal.

For a Workspace that already has a configuration, show a diff of the file instead of repeating the
whole TOML.

Configuration answers select the proposed state; they do not authorise side effects. After the
summary, take a separate **Proceed / Revise / Cancel** decision covering all of it, using the
native structured-question tool when it is available in the current mode and ordinary chat
otherwise. **Proceed** is what authorises the listed external installs and writes; it never
overrides any additional approval the host requires.

After confirmation, perform dependency changes first and rerun every probe. If any requirement is
still not ready, report what the command returned and stop before changing Workspace files. Once
the dependencies verify, create the approved directories, write the file and validate it.

## What setup may change

An approved dependency plan may use an existing package manager when it can supply the exact
release, or place an immutable upstream artifact in a user-owned tool directory and expose its
command through a user-writable directory on PATH. It may install npm or a Java runtime only when
the selected pinned tool needs it. The summary names this complete scope before anything changes;
an existing command at another version is left alone unless the plan explicitly names its
replacement.

For Workspace setup, ordinary file tools may create only:

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
order the user gave them. Write `cover-artwork = true` only when the reader asked for custom
covers. Add `[x4-crosspoint]` only when setup includes X4 and the user chose a host or destination
different from its default. Leaving a device value or the Cover Artwork key out is meaningful: the
validator reports it as `default` rather than `configured`, which keeps the file a record of
decisions instead of a copy of Galley's defaults.

## Validating, and the optional probe

Finish by invoking the read-only validator:

```
galley config validate --workspace WORKSPACE --json
```

Exit `0` means the configuration reads and every path it names can serve its role. Exit `3` means
it refused: read `refusal.boundary` and `refusal.summary`, correct the file, and validate again.
[The configuration contract](resources/workspace-config.md) lists what each boundary means.

Then, only when setup includes X4 and the applicable probe question granted permission:

```
galley device status --workspace WORKSPACE --json
```

This reads the device and writes nothing. An X4 that is asleep, in another mode, or off the
network refuses at `device-unavailable` — that is a fact about the device at that moment and says
nothing about the configuration, so report it and leave a validated setup complete.
