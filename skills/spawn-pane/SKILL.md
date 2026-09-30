---
name: spawn-pane
description: Spawn a herdr pane running a fresh coding agent and hand a task off to it. Use when the user wants work delegated to a new pane, an agent started beside the current one, or a prompt sent to and results collected from a herdr agent.
---

# spawn-pane

Delegate a task to a fresh agent in its own herdr pane: split, start, hand off, collect. Every herdr command replies with JSON — parse it rather than assuming success.

## Steps

1. **Split.** `herdr pane split --current --direction right --no-focus` (add `--cwd <path>` when the task lives in another repo or worktree). Done when the reply contains the new `pane_id` (shape `wX:pN`).
2. **Start.** `herdr agent start <name> --kind claude --pane <pane_id>` — derive `<name>` from the task (e.g. `type-review`); it is the handle every later agent command targets. On `agent_pane_busy`, poll `herdr pane process-info --pane <pane_id>` every few seconds until `foreground_process_group_id` equals `shell_pid` (the shell is back in the foreground), then re-run the start. Done when the reply is `agent_started` with `interactive_ready: true`.
3. **Hand off.** Pick the agent's **report file**: an absolute path `<dir>/<name>.md`, where `<dir>` is your scratchpad or another directory you own. Delete any existing file there. Then `herdr agent prompt <name> "<task>" --wait --until working --timeout 15000`. Write the prompt self-contained — repo, branch, the deliverable, whether the agent may modify code — and end it with: `When done, write your final report (what you did, results, anything you could not verify) to <report-file>, overwriting it.` Done when the reply is `agent_prompted` with `agent_status: working`.
4. **Collect.** Wait in the background — `herdr agent wait <name> --until idle --until done --until blocked --timeout 600000` — then read the report file and relay it. Done when the report's findings, not just the finished state, are reported back to the user.

## Report file

The report file is the result channel. It is a plain Markdown file so any `--kind` of agent can write it, and it outlives the pane — collect from it even after `agent_not_found`. A follow-up prompt to the same agent reuses the same path and **overwrites** it: delete the file, send the follow-up with the same closing instruction, collect again. A missing file after the wait means no report yet — then, and only then, `herdr agent read <name>` to diagnose: a `blocked` agent needs an answer; an `idle` one skipped the report and needs a re-prompt to write it.

## Traps

- **Panes die between turns.** A `pane_id` captured earlier may be gone by the next user message. On `agent_not_found` or any pane error, re-run `herdr pane list` and re-split from step 1 — the stale id will keep failing. Read the report file first; it may already hold the result.
- **Two id spaces.** `herdr agent …` subcommands target the agent *name*; `herdr pane …` subcommands target the *pane_id*.
- **Stalled prompts.** `--wait` requires a state change within 5s, otherwise it returns `agent_prompt_stalled`. Check `herdr agent get <name>`: `agent_status: working` means the prompt landed — go to step 4. Otherwise `herdr agent read <name>` to see what the pane is actually showing (a permission dialog, a crashed CLI); once the agent sits idle at its input, re-send the same prompt.
- **Other agent kinds.** `--kind` also accepts `codex`, `gemini`, `cursor`, and more — reach for one only when the user names it; `claude` is the default.
