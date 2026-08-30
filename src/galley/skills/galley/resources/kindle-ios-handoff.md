# Kindle for iOS: hand the Ready Artifact to the user

This path prepares one Galley-produced EPUB for user-controlled personal-document submission.
Galley publishes it as an immutable **Ready Artifact** inside the resolved Workspace and stops.
Local preparation is not evidence that Kindle accepted or converted the book, that a library item
appeared, or that it reads successfully on the device.

## Publish to Ready

Do not ask the user for an iCloud Drive folder, search for one, copy the EPUB into one or upload the
file to Kindle. The Workspace's `ready/` directory is the handoff boundary.

Once repair, localisation and Cover Artwork inputs are settled, use the ordinary Ready interface:

```text
galley prepare SOURCE \
  --profile kindle-ios-personal-documents \
  --ready \
  --json
```

Use `--workspace` when the user selected a non-default Workspace. Existing refusal rules remain in
force. A completed preparation may reuse an identical Ready Artifact or choose a hash-suffixed name
for different bytes; do not predict its filename or move it after publication. Read the exact path
from the completed Report.

## Report the local result and stop

Routine success starts with “It passed Galley's checks.” Render the exact artifact basename as
clickable text and use the absolute `artifact.path` as the link target without printing that path
again. Add only a reading caveat that materially matters. A routine handoff has no proactive
**Technical report** link; use one for a material caveat, refusal or ambiguity when helpful, or
when the user requests the retained details. Keep `artifact.sha256`,
`artifact.byte_size.value`, `profile.id`, `profile.profile_version`, checker counts and repair
declarations in the Report unless the person asks for them or they distinguish otherwise ambiguous
artifacts.

Then give one concise manual continuation:

> Upload or share this EPUB through your preferred Send to Kindle route.

Do not open Files, invoke a share sheet, contact Amazon, inspect sync state or claim that any later
step occurred. A refusal publishes no Ready Artifact; return its boundary, summary and retained
evidence instead.

If the person is testing the profile, ask them to bring back the submission date/time and route,
device and software versions, account region, whether Kindle accepted the file, whether a library
item appeared, and the title, author and cover observed there. Record each as their observation;
none follows from the local file.
