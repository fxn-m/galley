# Localising a document's remote images

A Markdown file saved from the web keeps its pictures where the website put them. `prepare` reads
local bytes for a Markdown source and retrieves nothing, so every one of those references is
unresolvable and the whole build refuses. That refusal is routine, and `galley localise` is its
answer: one explicit step that retrieves the images once into an evidence directory, then an
ordinary repair.

`prepare` stays fetch-free on purpose. If it fetched, the same stable file would build a different
book tomorrow — the CDN re-encodes an image, or answers 404 — and nothing would say so.

## Recognising it

Two Report facts together, and no judgement in between:

- the refusal boundary is `image-processing-failure`, and
- the references it names under `preparation.images` have `http` or `https` `src` values, with
  reason `unsupported-location`.

That pair means localisation, so localise and carry on. Ask the user only where something else is
true as well — the document is one they told you to leave alone, or the run is happening somewhere
that has no network. One approval covers the document; each picture is not a question.

## The sequence

### 1. Localise

```
galley localise ~/Documents/Galley/inbox/against-taste.md \
  --profile x4-crosspoint \
  --evidence-dir ~/Documents/Galley/work/against-taste.localised \
  --json
```

Exit `0` emits `galley/localisation/1`, and the directory now holds `report.json`,
`canonical-document.json`, `preservation-baseline.txt` and `images/`. Those first three are the
Repair Inputs; the images are the bytes the book will carry.

### 2. Read what it pulled

The document's `references` array is the evidence. Each entry names the locator, the host, the
addresses that host resolved to, how the transport ended, and the digest, size and **measured**
media type of what landed — measured from the bytes, never from the filename or the response
header. Check the count against the document, and check that the hosts are the ones the article's
own images would come from. Anything that surprises you is worth saying out loud before the bytes
enter a book.

### 3. Prepare from the Repair Set

```
galley prepare ~/Documents/Galley/inbox/against-taste.md \
  --profile x4-crosspoint \
  --output ~/Documents/Galley/work/against-taste.epub \
  --inspection-report ~/Documents/Galley/work/against-taste.localised/report.json \
  --canonical-document ~/Documents/Galley/work/against-taste.localised/canonical-document.json \
  --preservation-baseline ~/Documents/Galley/work/against-taste.localised/preservation-baseline.txt \
  --json
```

This is the ordinary agent-assisted path, unchanged. Galley proves the three inputs describe this
source and this profile, then normalises and packages the local bytes exactly as it would for a
document whose pictures were always on disk. `--expected-missing-tokens` is not needed:
localisation rewrites image locations and touches no word, so the baseline is the one the
inspection retained.

For a Workspace run, swap `--output` for `--ready` and its `--expected-source-hash`, as every
other candidate does. Keep the evidence directory somewhere `prepare` will not own — it refuses at
`output-is-input` rather than write over a file it is reading.

## Where it refuses, and what each one means

| Boundary | What happened |
|---|---|
| `no-remote-images` | The source references none. Nothing to do — the refusal you started from was something else. |
| `unlocalisable-reference` | A reference names neither a local file, an inline `data:` payload, nor an `http`/`https` locator. The summary and the fact both name the locator. A remote `cover-image` is **not** this: it is retrieved and rewritten like any other reference, and appears in the record under the identifier `cover-image`. |
| `blocked-image-host` | A host did not resolve, or resolved onto a private, loopback or link-local address. Galley refuses to fetch a received document's images from inside the network it is running on. |
| `unretrievable-image` | The transport failed, redirected, exceeded the 32 MiB ceiling, or returned bytes that do not measure as an image. The fact names which reference and why. |
| `unsupported-source-kind` | The source is an Article-Like Page URL, whose images preparation already retrieves itself. Prepare it directly. |
| `output-exists` | The directory already holds a Repair Set. `--overwrite` is the only permission to replace one. |

Every one of these refuses the run whole and writes nothing. A Repair Set missing one picture
would be refused by the very `prepare` it exists to feed, and a partial one on disk looks
finished.
