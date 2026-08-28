# Harness-native questions for Galley setup

Quick primary-source pass, 2026-08-28. The useful conclusion is that Galley should specify the
*decision it needs* and let the active harness render that decision through its native question
surface when one is available. It should not assume one universal tool name or schema.

## What the harnesses actually expose

### Claude Code

Claude Code's `AskUserQuestion` asks one to four questions per call. Each question has a header of
at most 12 characters, two to four labelled options with descriptions, and a `multiSelect` flag.
The Agent SDK documentation also says that `AskUserQuestion` is not available to Agent-tool
subagents. [Claude Code: handle approvals and user input](https://code.claude.com/docs/en/agent-sdk/user-input)

Free text is a presentation detail. The Agent SDK tells application authors to add an **Other**
choice and return the user's actual text as the answer. Anthropic's first-party plugin-development
guide describes **Other** as automatic in Claude Code itself. In other words, a skill may invite a
custom answer, but should not manufacture an `Other` option if the live tool says the host already
adds it. [Agent SDK free-text guidance](https://code.claude.com/docs/en/agent-sdk/user-input#support-free-text-input),
[Claude Code interactive-command guide](https://github.com/anthropics/claude-code/blob/main/plugins/plugin-dev/skills/command-development/references/interactive-commands.md#askuserquestion-basics)

Claude's documentation explicitly separates two reasons for interrupting the user: permission to
run a tool, and a clarifying question. Both can pause execution through the SDK, but they are not
the same decision. A configuration answer therefore should not silently double as approval for an
installation. [Claude Code: detect when Claude needs input](https://code.claude.com/docs/en/agent-sdk/user-input#detect-when-claude-needs-input)

### Codex in the current desktop harness

OpenAI's product guidance is behavioral: ask only when missing information would materially change
the answer or create meaningful risk; ask for the smallest missing field; and express judgment
calls such as when to clarify as decision rules. It also recommends putting tool-specific behavior
in the tool description. [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.5)

The current open-source Codex implementation supplies the concrete picker schema: prefer one and
permit at most three questions; give each question a header of at most 12 characters and two or
three mutually exclusive choices; put the recommended choice first and suffix its label with
`(Recommended)`; and omit **Other** because the client adds it. The implementation computes tool
availability from the active harness modes rather than promising that it exists everywhere.
[Codex `request_user_input` schema](https://github.com/openai/codex/blob/main/codex-rs/core/src/tools/handlers/request_user_input_spec.rs)

This session's live `request_user_input` contract matches that implementation and narrows its mode
availability:

- it is available only in Plan mode;
- one call accepts one to three questions;
- each question has a header of at most 12 characters and two or three mutually exclusive choices;
- the recommended choice goes first and its label ends in `(Recommended)`;
- the client adds a free-form **Other** choice, so the agent must not add one;
- the schema has no multi-select field.

The quick official-docs search did not find a stable OpenAI product page that promises those exact
limits across Codex clients and versions. Treat them as capabilities to detect and obey at runtime,
not facts to bake into Galley's portable product contract.

Codex also models execution approval and structured user input as separate protocol events. That
supports the same product rule as Claude: a configuration choice is not automatically permission
to perform an install or write. [Codex protocol](https://github.com/openai/codex/blob/main/codex-rs/docs/protocol_v1.md#interface)

## Consequence for the current setup conversation

Galley's current instruction to ask all six configuration questions in one message cannot use the
native picker in either harness: Claude Code tops out at four questions, while this Codex surface
tops out at three and is unavailable outside Plan mode. A six-question prose form can preserve the
"all defaults" shortcut, but it bypasses the native pickers and their descriptions and validation.

The better interaction is progressive:

1. Perform the read-only dependency and existing-configuration inventory first.
2. Ask one fast-path question: **use Galley's recommended configuration, or customise it?**
3. If the user accepts the defaults, ask no further configuration questions.
4. If they customise, ask only unresolved decisions, in batches that fit the live tool. Use
   structured choices for bounded decisions and its free-form route (or ordinary chat) for paths,
   hostnames, and other arbitrary strings.
5. Present the complete proposed configuration and exact installation/write plan.
6. Obtain a separate explicit **proceed / revise / cancel** decision. Execution can still trigger a
   distinct host security or tool-permission approval.

## Recommended portable instruction

The setup skill can use wording along these lines:

> After the read-only inventory, ask only for choices that cannot be discovered safely. If the
> current harness exposes a native structured-question tool in the current mode, use it and obey
> its live schema; do not change modes merely to obtain a picker. Otherwise ask the same compact
> questions in ordinary chat.
>
> Start with one choice between **All recommended defaults** and **Customise**. If the user chooses
> the defaults, skip the remaining configuration questions. If they customise, ask only the
> affected questions, at most three at a time, with a short header, the recommended answer first,
> and one-sentence descriptions of the consequences. Keep choices mutually exclusive unless the
> live tool explicitly supports multi-select. Do not add an **Other** option when the host supplies
> one; accept free text for paths, names, and hosts.
>
> Configuration answers select the proposed state; they do not authorise side effects. After all
> answers, show the exact dependency installs, destinations, PATH/profile changes, directories,
> and TOML. Then ask a separate **Proceed / Revise / Cancel** question. Do not install or write
> until the user chooses **Proceed**, and do not treat that answer as a way around any additional
> approval the host requires.

This portable baseline uses no more than three questions or three options and does not depend on
multi-select, so it fits both known native surfaces. A harness with richer capabilities can still
render the same decisions more richly without changing Galley's setup policy.
