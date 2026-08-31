# Kindle for iOS: hand the Ready Artifact to the user

This path prepares one Galley-produced EPUB for user-controlled personal-document submission.
Galley publishes it as an immutable **Ready Artifact** inside the resolved Workspace. The agent
then follows any applicable user-authorised transfer instruction.
Local preparation is not evidence that Kindle accepted or converted the book, that a library item
appeared, or that it reads successfully on the device.

## Publish to Ready

By default, hand over the file in the Workspace's `ready/` directory. No folder search or transfer
is needed. When the current request or saved customisation specifies a transfer, follow
[the customisation guide](customisation.md) for its scope and authorisation. Transfer only the
final checked EPUB after requested cover work is complete; retain the published original.

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

## Report the result and leave Kindle submission to the user

Routine success starts with “It passed Galley's checks.” Render the exact artifact basename as
clickable text and use the absolute `artifact.path` as the link target without printing that path
again. Add only a reading caveat that materially matters. A routine handoff has no proactive
**Technical report** link; use one for a material caveat, refusal or ambiguity when helpful, or
when the user requests the retained details. Keep `artifact.sha256`,
`artifact.byte_size.value`, `profile.id`, `profile.profile_version`, checker counts and repair
declarations in the Report unless the person asks for them or they distinguish otherwise ambiguous
artifacts.

If a transfer was requested, report its confirmed result or blocker. Then give one concise manual
continuation:

> Upload or share this EPUB through your preferred Send to Kindle route.

Submission to Kindle remains user-controlled. Do not contact Amazon, inspect sync state or claim
that a transfer proves Kindle acceptance. A refusal publishes no Ready Artifact; return its
boundary, summary and retained evidence instead.

If the person is testing the profile, ask them to bring back the submission date/time and route,
device and software versions, account region, whether Kindle accepted the file, whether a library
item appeared, and the title, author and cover observed there. Record each as their observation;
none follows from the local file.
