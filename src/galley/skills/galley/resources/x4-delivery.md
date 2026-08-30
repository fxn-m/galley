# X4: continue from preparation into separately authorised Delivery

This branch begins only after one-source X4 preparation has published its Ready Artifact. Assisted
Preparation is complete; Delivery is a separate action with its own fresh evidence and authority.

## Read the plan underneath the conversation

Resolve the logical host and destination from the Workspace or the user's explicit request, then
freeze the Ready Artifact, logical host and destination in the read-only command:

```text
galley deliver READY --plan --json --host HOST --destination DESTINATION
```

Read the Delivery Record without narrating its path, hashes, resolved addresses, exchange evidence
or formal planning vocabulary. The plan's artifact, device, destination and action are the facts
that decide the next conversational step.

## Authorise the exact consequence

When the plan identifies X4 and its exact action is `upload-new`, ask only: “Send it to X4?” A bare
affirmative answer authorises that immediately preceding Ready Artifact, logical host, destination
and `upload-new` action. It carries no overwrite authority and no authority for another artifact or
later plan. Artwork and send are never one question.

After approval, run the explicit values from that plan:

```text
galley deliver READY --json --host HOST --destination DESTINATION
```

The command repeats Ready Artifact validation, target resolution, X4 identification and destination
preflight before writing. If those fresh facts still support `upload-new`, send once and confirm it
from the destination listing. A newly resolved mDNS or DHCP address that is still a freshly
validated local address and still answers as the same X4 does not invalidate approval of the
logical host.

## Branch on the fresh result

- `already-delivered`: say the exact file is already on the X4; no upload occurred.
- `destination-collision`: explain that the same name belongs to different bytes and present the
  replacement decision. Only a separate explicit approval that names replacement authorises the
  following command.

```text
galley deliver READY --json --host HOST --destination DESTINATION --overwrite
```

- A changed artifact or destination, an untrusted target, or a device that no longer identifies as
  X4 invalidates the earlier approval. Stop before writing and explain what changed.
- An unreachable device gets one concrete next action: wake the device or put it in the appropriate
  transfer mode, then make a fresh plan.
- An Unconfirmed Delivery says the upload may have landed but the X4 did not confirm it. Keep the
  Ready Artifact unchanged and begin any later approved attempt from a fresh plan.

Translate the concrete outcome and next action. Low-level exceptions, addresses, transports and
record paths stay in retained evidence until the user asks. Direct `galley deliver` invocation is
already non-interactive authorization; this conversational approval applies only to this
one-source continuation and leaves the Inbox run's finite batch approval unchanged.
