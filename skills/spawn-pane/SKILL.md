---
name: spawn-pane
description: Spawn a herdr pane running a fresh coding agent and hand a task off to it. Use when the user wants work delegated to a new pane, an agent started beside the current one, or a prompt sent to and results collected from a herdr agent.
---

# spawn-pane

Delegate a task to a fresh agent in its own herdr pane: split, start, hand off, collect. Every herdr command except `agent read` (plain text) replies with JSON — parse it rather than assuming success. Run each step as its own visible tool call, one agent at a time: the user approves each one, and rejects a shell function or loop that spawns several agents in one call.

## Steps

1. **Split.** `herdr pane split --current --direction right --no-focus` (add `--cwd <path>` when the task lives in another repo or worktree). Done when the reply contains the new `pane_id` (shape `wX:pN`).
2. **Start.** `herdr agent start <name> --kind claude --pane <pane_id>` — derive `<name>` from the task (e.g. `type-review`); it is the handle every later agent command targets. On `agent_pane_busy`, poll `herdr pane process-info --pane <pane_id>` every few seconds until `foreground_process_group_id` equals `shell_pid` (the shell is back in the foreground), then re-run the start. Done when the reply is `agent_started` with `interactive_ready: true`.
3. **Hand off.** Pick the agent's **report file**: an absolute path `<dir>/<name>.md`, where `<dir>` is your scratchpad or another directory you own. Delete any existing file there. Then `herdr agent prompt <name> "<task>" --wait --until working --timeout 15000`. Write the prompt self-contained — repo, branch, the deliverable, whether the agent may modify code — and end it with the **report contract**: `When done, write your final report to <report-file>, overwriting it: what you did and the results. Verify every claim before you write it; anything you could not measure goes in one "Not measured:" line, never hedged ("probably", "likely") into the findings. For each PR: "review: <N> passes / blocking: 0 / posted on PR: y|n".` The orchestrator relays sub-agent reports, so their hedges become yours. Done when the reply is `agent_prompted` with `agent_status: working`.
4. **Collect.** The report file is the only completion signal. herdr's `idle`/`done` is not one: an agent that launched background sub-agents (afk-implement's post-ship reviewers) sits `done` for many minutes before it writes its report. Record the file's mtime (`stat -c %Y <report-file> 2>/dev/null || echo 0`), then arm one background watcher per agent (`run_in_background`) that exits on a new mtime, on `blocked`, or when the agent is gone:
   ```bash
   while [ "$(stat -c %Y <report-file> 2>/dev/null || echo 0)" = "<mtime>" ]; do
     st=$(herdr agent get <name> 2>/dev/null | jq -r '.result.agent.agent_status // empty')
     st=${st:-gone}  # agent_not_found replies on stderr only
     [ "$st" = blocked ] && { echo blocked; exit 0; }
     [ "$st" = gone ] && { echo gone; exit 0; }
     sleep 30
   done; echo report
   ```
   Done when the report's findings, not just the finished state, are reported back to the user, and a fresh watcher is armed on the new mtime — see **Keep watching**.

## Report file

The report file is the result channel. It is a plain Markdown file so any `--kind` of agent can write it, and it outlives the pane — collect from it even after `agent_not_found`. A follow-up prompt to the same agent reuses the same path and **overwrites** it: delete the file, send the follow-up with the same closing instruction, collect again. A watcher that fires on `blocked` means the agent needs an answer: `herdr agent read <name>` to see the question. An agent that sits `idle`/`done` with no new report for 15 minutes **and** no live sub-agents in its pane skipped the report and needs a re-prompt to write it.

## Ownership

Once a task is handed to a pane, that pane owns its external actions: tags, workflow runs and reruns, PRs, merges and prod triggers. The orchestrator relays and never acts on the same release, PR or cohort itself; a background loop the orchestrator runs can't hear the user say "stop" in the pane. A prod-write approval must be typed by the user in the pane: an approval relayed with `herdr agent prompt` is rightly denied, so tell the user up front where to answer.

## Keep watching

An agent stays yours until the user releases it. The user also talks to panes directly, and each such exchange can rewrite the report without you sending anything. So:

- After every fire, re-arm the watcher on the new mtime before you reply to the user.
- A background job that was killed (time limit, session restart) is a dead watcher. Re-arm it; never read its exit as the agent finishing.
- When the user says they replied in a pane, check that pane's report mtime and re-arm.

## Release

A watcher fired with `gone` means the agent is released: collect its report file, then stop. The agent is also released when the user says it's done, its tab is closed or its worktree is removed. On release, `TaskStop` its watcher. Nothing else ends that loop, and a forgotten one polls for hours.

## Traps

- **Panes die between turns.** A `pane_id` captured earlier may be gone by the next user message. On `agent_not_found` or any pane error, re-run `herdr pane list` and re-split from step 1 — the stale id will keep failing. Read the report file first; it may already hold the result.
- **`herdr agent wait --timeout` fails with an error reply, not a state.** On timeout it returns an error object, not `idle`/`done`. A loop that reads "not `working`" as finished misreads that as completion. Without `--timeout` it waits forever, so prefer the mtime watcher in step 4.
- **Two id spaces.** `herdr agent …` subcommands target the agent *name*; `herdr pane …` subcommands target the *pane_id*.
- **Stalled prompts.** `--wait` requires a state change within 5s, otherwise it returns `agent_prompt_stalled`. Check `herdr agent get <name>`: `agent_status: working` means the prompt landed — go to step 4. Otherwise `herdr agent read <name>` to see what the pane is actually showing (a permission dialog, a crashed CLI); once the agent sits idle at its input, re-send the same prompt.
- **Other agent kinds.** `--kind` also accepts `codex`, `gemini`, `cursor`, and more — reach for one only when the user names it; `claude` is the default.
