# The Workspace Configuration contract

One strict TOML schema, `galley/workspace-config/1`, governs the file. It lives at
`galley.toml` in the Galley Workspace, and it is the only configuration Galley has.

## Which Workspace a command resolves

Fixed precedence, with no search of the current directory or its parents:

1. an explicit `--workspace PATH`;
2. the `GALLEY_HOME` environment variable;
3. `~/Documents/Galley`, the visible default.

Pass `--workspace` explicitly during setup, so the Workspace being configured is the one being
validated whatever the environment says.

## Keys

| Table | Key | Type | Meaning |
|---|---|---|---|
| top level | `version` | integer | `1` is the only supported version. |
| top level | `cover-artwork` | boolean | Optional. Custom covers when `true`. Absence or `false` means off. |
| `[customisation]` | `instructions` | string | User-authored reading preferences. Required when the optional table is present; empty clears preferences. |
| `[[inbox]]` | `name` | non-empty string | How this Inbox is reported. Unique across the file. |
| `[[inbox]]` | `path` | non-empty string | Where the Inbox is. See resolution below. |
| `[[inbox]]` | `recursive` | boolean | Required, with no default: `true` descends ordinary subdirectories, `false` reads direct children. |
| `[x4-crosspoint]` | `host` | non-empty string | CrossPoint host, optionally `HOST:PORT`. Defaults to `crosspoint.local`. |
| `[x4-crosspoint]` | `destination` | non-empty string | Device folder that receives books. Defaults to `/`. |

`[[inbox]]` is a non-empty array of tables, and its order is significant: when two Inboxes can see
the same file, the first configured one owns primary attribution and the others are reported
alongside it.

An Inbox `path` resolves by its own spelling. A leading `~` is home-relative, an absolute path is
taken as written, and anything else resolves against the Galley Workspace — so `path = "inbox"`
means the Inbox inside the Workspace. The validator reports which of the three happened, so a
spelling can be checked against what it resolved to.

## An annotated file

```toml
# Galley Workspace Configuration. Galley reads this file and never writes it.
version = 1

# Resolves against the Workspace: <workspace>/inbox
[[inbox]]
name = "inbox"
path = "inbox"
recursive = false

# Home-relative, and read recursively. This directory must already exist.
[[inbox]]
name = "reading"
path = "~/Documents/Reading"
recursive = true

# Only values the user actually chose belong here; an omitted one is reported as `default`.
[x4-crosspoint]
host = "crosspoint.local"
destination = "/Books"
```

## Customisation

Keep recurring preferences in this optional section, for example:

```toml
[customisation]
instructions = """
Use restrained geometric artwork for custom covers.
"""
```

The validator exposes the text unchanged as `customisation.instructions`, with `source` set to
`configured`. Omitting the table yields an empty string with source `default`. A present table
needs a string `instructions`; other keys refuse. The CLI neither interprets nor executes this
text. Agent behaviour, saving authority and current-request overrides are defined in
[the customisation guide](../../galley/resources/customisation.md).

## Galley-owned locations

`work/`, `ready/`, `ready/evidence/` and `delivery/` beneath the Workspace have fixed roles and
cannot be pointed elsewhere: retained evidence from a refused attempt, immutable Ready Artifacts,
the Ready evidence collection, and immutable Delivery Records. The CLI creates none of them, which
is why setup does.

`config validate` reports each of `work`, `ready` and `delivery` with a state. `absent` is a fact
rather than a fault — the CLI never creates one — but a path of the wrong kind refuses, because a
`ready` occupied by a regular file cannot serve its role and finding that out at publication time
would be worse.

## What the validator refuses

Each refusal names a boundary, and every fact gathered before it stopped is still reported.

| Boundary | What produced it |
|---|---|
| `workspace-configuration-missing` | No `galley.toml` in the resolved Workspace. |
| `unreadable-workspace-configuration` | The file exists and could not be read. |
| `invalid-workspace-configuration` | Not valid TOML, or a table with a missing or wrongly typed value. |
| `unknown-configuration-key` | A key the schema does not define, at the top level or in any table. The refusal lists the accepted keys. |
| `unsupported-configuration-version` | `version` is absent or is not `1`. |
| `duplicate-inbox-name` | Two `[[inbox]]` tables share a `name`. |
| `inbox-unavailable` | A configured Inbox is absent, a regular file, or unreadable. The configured order decides which one is named. |
| `workspace-location-unusable` | A Galley-owned location exists as the wrong kind of path. |

Correct the file and validate again. A refusal reports; the fix is yours and the user's.
