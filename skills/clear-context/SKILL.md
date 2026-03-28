---
name: clear-context
description: Prepare a compact handoff when the user wants to clear or compress context without losing progress. Use when the user asks to clear context, reset the thread, start fresh, continue in a new chat, or generate a handoff summary for the current task. Capture only durable state such as the active goal, decisions, files changed, verification status, blockers, and the next action.
---

# Clear Context

Create a minimal handoff for another Codex instance or a fresh chat. Keep only the information that still matters after the conversation history is gone.

## Workflow

1. Identify the active task and the current stopping point.
2. Gather durable state only:
   - current goal
   - completed work
   - files changed or created
   - commands run and their meaningful outcomes
   - validation completed and validation still missing
   - blockers, assumptions, and the next action
3. Drop context that will not help the next agent:
   - long logs
   - repeated reasoning
   - speculative alternatives that were not chosen
   - large diffs that can be inspected directly from the repo
4. State limits plainly. Do not claim the context is actually erased; provide a restart packet that makes a fresh chat viable.
5. If repository state matters, inspect it and mention only the facts that affect the next step.

## Output Format

Use this shape unless the user requests a different format:

```text
Current goal:
Completed:
Files changed:
Verification:
Open issues:
Next step:
Restart prompt:
```

## Writing Rules

Write short bullets or short paragraphs.

Include concrete file paths, command names, and test outcomes when known.

Say explicitly when validation was not run or failed.

Separate confirmed facts from assumptions.

Prefer one restart prompt that another agent can act on immediately.

## Restart Prompt Pattern

Use a final prompt like this:

```text
Use the repo at <path>. Resume from this handoff:
- Goal: <current goal>
- Next step: <immediate action>
- Files to inspect first: <paths>
- Verification status: <done or missing>
- Open issue: <main blocker or risk>
```
