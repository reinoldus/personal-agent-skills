---
name: spawn-pane
description: Spawn a herdr pane running a fresh coding agent and hand a task off to it. Use when the user wants work delegated to a new pane, an agent started beside the current one, or a prompt sent to and results collected from a herdr agent.
---

# spawn-pane

Delegate a task to a fresh agent in its own herdr pane: split, start, hand off, collect. Every herdr command replies with JSON — parse it rather than assuming success.

## Steps

1. **Split.** `herdr pane split --current --direction right --no-focus` (add `--cwd <path>` when the task lives in another repo or worktree). Done when the reply contains the new `pane_id` (shape `wX:pN`).
2. **Start.** `herdr agent start <name> --kind claude --pane <pane_id>` — derive `<name>` from the task (e.g. `type-review`); it is the handle every later agent command targets. Done when the reply is `agent_started` with `interactive_ready: true`.
3. **Hand off.** `herdr agent prompt <name> "<task>" --wait --until working --timeout 15000`. Write the prompt self-contained: repo, branch, the deliverable, and whether the agent may modify code. Done when the reply is `agent_prompted` with `agent_status: working`.
4. **Collect.** Wait in the background — `herdr agent wait <name> --until idle --until done --until blocked --timeout 600000` — then `herdr agent read <name>` and relay what the agent produced. Done when the findings themselves, not just the finished state, are reported back to the user.

## Traps

- **Panes die between turns.** A `pane_id` captured earlier may be gone by the next user message. On `agent_not_found` or any pane error, re-run `herdr pane list` and re-split from step 1 — the stale id will keep failing.
- **Two id spaces.** `herdr agent …` subcommands target the agent *name*; `herdr pane …` subcommands target the *pane_id*.
- **Stalled prompts.** `--wait` requires a state change within 5s, otherwise it returns `agent_prompt_stalled`. On stall, `herdr agent read <name>` to see what the pane is actually showing (a permission dialog, a crashed CLI) before re-prompting.
- **Other agent kinds.** `--kind` also accepts `codex`, `gemini`, `cursor`, and more — reach for one only when the user names it; `claude` is the default.
