# Agent handoffs and pull requests

## Give a builder their next prompt

1. Send the repository URL, prerequisite merge SHA, and a single Markdown file from `docs/prompts/`. Ask the builder to provide the prompt file to their coding agent with access to that checkout. On the first handoff include this kit's README and [Setup](SETUP.md).
2. Start a clean topic branch from reviewed `main` using the branch name in the prompt. If a prerequisite has yet to merge, keep independent work on the written contract and mock boundary. For acceptance marked blocked, record which PR or setup input is missing. The branch should remain reviewable on its declared base.
3. The agent reads the prompt's inputs and inspects the allowed paths before editing. Keep one milestone prompt per PR and isolate edits to the listed owners. Run the task's acceptance checks after implementation. The agent reports actual output, including skipped and blocked checks. The developer reviews the diff and opens the PR.
4. A verifies the predecessor SHA, file ownership, shared boundary and risk. B reviews changes to the B ports or remote behavior. C reviews event and PCM changes. Merge the smallest passing PR into `main`. Re-run the milestone integration checks at the merged SHA. Record G0–G6 evidence in the PR or linked run note.

## Common agent instructions

- Use the TDD and frozen contract as the source of truth. Read the existing repository to distinguish already landed work from proposed paths. The only assumed inputs at K0 are this kit's files.
- Stay in scope and avoid broad refactors. When a dependency or contract question blocks progress, report exact paths, expected vs observed behavior and a proposed decision. Do the independent portion using the approved fixture or mock. Code and test against the actual JSON rather than inventing a second fixture dialect.
- Run network/provider/model commands only in later prompts that call for an authorized opt-in check. Treat external integration as pending until verified on a real service or device. Use process env or local ignored config. Redact secrets, transcript contents, raw provider bodies and local credentials from evidence.
- Generated or checked-equivalent types are tracked by the owning lane. Contract changes go through A. After G0 pair schema and fixture changes with compatibility/version notes before changing implementation. Keep mocks test-only and label saved replay clearly.

## Evidence to hand back

Copy this into the PR description or handoff message.

```text
Prompt and milestone:
Branch, base SHA, head SHA:
Changed files:
Contract consumed or proposed change:
Acceptance commands and results:
Manual checks with environment and observed result:
Tests blocked or skipped, and exact reason:
Assumptions or tuning changes:
Downstream builder, merge/dependency required, and next check:
```

For sharing between lanes, include fixture IDs, actual event sequence or scrubbed provider field ordering, selected config values, and output counts as applicable. For latency give sample size and p50/p95 with units. Screenshots or clips require appropriate consent and should reflect the actual mode. Every milestone has a cross-lane checkpoint in [Acceptance](ACCEPTANCE.md).

## Contract issue path

Open a short issue or PR for a wire or port change. Include a minimal scrubbed event/fixture that exhibits the problem, expected and observed behavior, affected decision numbers, the proposed schema/interface change, and migration cost. Contact A and affected owners. Continue compatible work while the change is reviewed. Record the resolved decision and retest both languages before advancing the shared version.
