# Galley's command contract

`inspect`, `prepare` and `audit` each emit one canonical Report. `--json` selects it on stdout;
without it stdout carries a concise rendering of the same in-memory data, never a second source of
truth. JSON stdout contains only JSON.

Commands outside those three emit their own versioned command document instead, because Workspace,
Inbox, device, Delivery and localisation facts are not one of the Report's five source/artifact
categories. The envelope says which of the two you are holding: a Report carries
`galley.report_schema`, always `galley/report/1`, and a command document carries
`galley.document_schema` naming its own.

`localise` is both: it emits `galley/localisation/1` on stdout and *writes* a canonical Report
into its evidence directory, because that Report is one of the three Repair Inputs it produces.
Its `galley.command` reads `localise`, and `prepare` accepts it exactly as it accepts an
`inspect` Report.

## Commands this release exposes

| Command | What it does |
|---|---|
| `galley profiles list` | Lists Device Profiles. |
| `galley profiles show PROFILE` | Emits one fully assembled Device Profile. |
| `galley inspect SOURCE --profile PROFILE` | Reads a source and projects what its artifact would carry. Writes nothing unless asked. |
| `galley prepare SOURCE --profile PROFILE --output PATH` | Builds an audited EPUB3 and publishes it with its evidence. |
| `galley audit EPUB --profile PROFILE` | Assesses an existing EPUB read-only, however it was produced. |
| `galley localise SOURCE --profile PROFILE --evidence-dir DIR` | Retrieves the remote images a Markdown source references, once, into a Repair Set an ordinary agent-assisted `prepare` then consumes. The only command that fetches for a Markdown source. Emits `galley/localisation/1`. |
| `galley config validate` | Reports what the Workspace Configuration resolves to. Read-only: it writes nothing and inventories no Inbox. Emits `galley/config-validation/1`. |
| `galley inbox check` | Inventories every configured Inbox once and reports each candidate's state. Read-only: it watches nothing and processes no source. Emits `galley/inbox-check/1`. |
| `galley device status` | Reports what the configured CrossPoint device is, without reading or writing a book. Emits `galley/device-status/1`. |
| `galley deliver` | Plans or performs one Delivery of one Ready Artifact and persists an immutable Delivery Record. `--plan` reads the device and destination without uploading. Emits `galley/delivery-record/2`; historical v1 records remain valid. |
| `galley skill install` | Installs both version-matched Agent Skills into the standard user skills directory, or an explicit `--target`. Emits `galley/skill-installation/1`. |
| `galley skill uninstall` | Removes only the files a Galley installation put there, retaining and reporting everything else. |

`SOURCE` is a local Markdown path or a live Article-Like Page URL. A local `.html` file is
refused: HTML enters only through a live fetch.

## Options that matter to a run

| Option | Command | Effect |
|---|---|---|
| `--ready` | `prepare` | Publishes the audited book as an immutable Ready Artifact inside the resolved Workspace, with its own evidence bundle, instead of to an `--output` path. Exactly one of the two is given. |
| `--expected-source-hash HASH` | `prepare` | The SHA-256 an Inbox Check observed for the source. Galley checks it before and after acquisition and refuses on a mismatch, so a source that changes under a run publishes nothing. |
| `--plan` | `deliver` | Reads the device and the destination listing and records one exact action, without touching the upload endpoint. |
| `--host HOST[:PORT]` | `deliver` `device status` | Overrides the configured CrossPoint host for this invocation only. |
| `--destination DIR` | `deliver` | Overrides the configured absolute CrossPoint folder for this invocation only. |
| `--timeout SECONDS` | `deliver` `device status` | A finite positive timeout; status defaults to three seconds and Delivery to thirty. No invocation ever waits forever. |
| `--evidence-dir DIR` | `localise` | Required. The directory the Repair Set and the retrieved bytes are written into. Nothing outside it is written, and the source is never mutated. |
| `--evidence-dir DIR` | `inspect` | Retains `report.json`, `canonical-document.json`, `preservation-baseline.txt` and, for an extracted page, `extraction.html`. Without it, `inspect` has no side effects. |
| `--evidence-dir DIR` | `prepare` | Places the companion evidence directory. `prepare` always writes one; its default name is the output stem plus `.galley`. It must not be the directory holding the Repair Inputs — every file a command reads is protected from its own outputs, so the run refuses at `output-is-input` rather than overwrite one. |
| `--report-out PATH` | all three | Writes the canonical Report in addition to the selected stdout rendering. |
| `--workspace PATH` | `config validate` `inbox check` `device status` `deliver` `prepare --ready` | Resolves one named Galley Workspace instead of `GALLEY_HOME` or the visible default under the user's Documents directory. |
| `--target PATH` | `skill install` `skill uninstall` | Manages one named skills directory instead of the standard user location. |
| `--force` | `skill install` | Replaces the two Galley skill directories when they are no longer the ones Galley installed. It authorises nothing outside those two, and `skill uninstall` accepts no such option at all. |
| `--overwrite` | `localise` | The only permission to replace an existing Repair Set in the evidence directory. |
| `--overwrite` | all three | The only permission to replace a command-owned output. It never permits mutating a source, Report, Canonical Document, Preservation Baseline or audited EPUB. |
| `--overwrite` | `deliver` | Permits replacing a differently-sized file already at the exact destination filename. Without it a size-mismatched collision refuses; a same-size match is `already-delivered` and uploads nothing either way. |
| `--expected-missing-tokens FILE` | `prepare` | A UTF-8 JSON object mapping exact word tokens to allowed missing counts. Omitting it means no missing token is expected. |
| `--inspection-report` `--canonical-document` `--preservation-baseline` | `prepare` | The three Repair Inputs. They are supplied together or not at all. |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | The command completed. `audit` stays `0` even when requirements evaluate false, because audit has no refusal authority over its subject. |
| `2` | An invocation syntax error before a workflow existed — a missing argument, or an invalid option combination such as two of the three Repair Inputs. No Report is emitted. |
| `3` | A schema-valid Report or command document was emitted with `outcome: refused` at a known boundary — execution, source, Compatibility, preservation or configuration. |
| `4` | An internal invariant failed. No candidate EPUB is published. |
| `5` | An Unconfirmed Delivery: an upload may have begun, but a fresh destination listing did not confirm the bytes. Neither success nor refusal — the device may or may not hold the book, and a retry re-plans from scratch. Only `deliver` emits it. |

A syntactically valid invocation always attempts to emit its Report, including a structured
refusal. Read the Report rather than the exit code alone: the refusal names its boundary, its
stage, the facts gathered before it stopped, and — where Galley inferred rather than observed —
the basis for the inference.

## What the CLI will not do

`prepare` alone may refuse a build; `localise` refuses a localisation and never a build. `audit`
reports and never refuses or mutates its subject.
`inspect` may project a later refusal without promising to predict it. None of the three emits a
recommendation, a score, a readiness label or a Reading Verdict; those belong to you and to the
human reader respectively.
