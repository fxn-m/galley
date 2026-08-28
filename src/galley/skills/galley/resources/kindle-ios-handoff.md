# Kindle for iOS: stop at the user-controlled handoff

This path prepares one Galley-produced EPUB for the person to share from iOS Files. Galley stops
at the local iCloud Drive path. The EPUB there is a **Submission Artifact**, not evidence that an
iCloud sync, Kindle share, Amazon conversion, library arrival or successful read happened.

## Confirm the two destinations

Use an exact Handoff Folder the user has already named or confirmed. If they have not supplied
one, ask for it before preparation. Never search for iCloud containers, scan likely folders or
choose a location on their behalf.

Name the final `.epub` inside that Handoff Folder. Ask for or choose a Galley evidence location
that is outside the Handoff Folder, then show the two resolved paths. The evidence directory must
not equal the Handoff Folder or sit below it. Shell-quote real paths that contain spaces.

Put no Report, preview, cover source, assessment or helper file in the Handoff Folder. Galley
does not inspect iCloud sync state, watch either folder or contact Amazon.

## Prepare once through the ordinary interface

```text
galley prepare SOURCE \
  --profile kindle-ios-personal-documents \
  --output CONFIRMED_HANDOFF_FOLDER/BOOK.epub \
  --evidence-dir GALLEY_EVIDENCE/BOOK.galley \
  --json
```

Use the same repair and cover-authoring paths as any ordinary preparation when the source needs
them. Existing refusal and overwrite rules remain in force. In particular, report an
`output-exists` refusal and ask what the user wants; never add `--overwrite` merely to finish the
handoff. Run once and stop—there is no retry loop, watcher, iCloud API, Amazon credential or
upload command in this path.

## Report only what preparation proved

On a completed Report, read and return:

- `artifact.path` as the exact Submission Artifact path;
- `artifact.sha256` and `artifact.byte_size.value`;
- `profile.id` and `profile.profile_version`;
- the external evidence-directory path, whose `report.json` records this run.

Confirm that the artifact path is the path requested and that the Handoff Folder received only
the EPUB from this run. Local presence proves no later step. A refusal publishes no Submission
Artifact; return its boundary, summary and retained evidence path instead of continuing.

Then give one concise instruction:

> On iPhone, open the EPUB in Files, share it to Kindle, confirm the intended title and author,
> and wait for the library item.

Ask the person to bring back the share date/time and route, iPhone model, iOS version, Kindle app
version, account region, whether the Kindle share action accepted the file or displayed a failure,
whether a library item appeared, and the title, author and cover they observed there. Record each
as their observation; none follows from the local file.
