---
name: spawn-worktree
description: Create a git worktree with worktrunk (`wt`), open it as its own herdr workspace running a fresh coding agent, and hand a task off to it. Use when the user wants work done on a separate branch in parallel, an isolated worktree for a feature or fix, or a sibling agent started outside the current checkout.
---

# spawn-worktree

Branch the work off into its own worktree and its own agent: name, create, attach, hand off, collect. The invoking agent stays where it is — the new agent is a sibling, not a replacement. Every herdr command replies with JSON; parse it rather than assuming success.

## Steps

1. **Agree the branch name.** Propose `<type>/<slug>` — `feat/add-retry`, `fix/flaky-test` — and include the issue number when one exists: `feat/123-add-retry`. Ask the user to confirm before creating anything. Done when the user has approved a name; never auto-create one.
2. **Create the worktree.** `wt switch --create <branch>`. worktrunk runs the project's configured pre-start hooks here — dependency install, per-worktree env files, port allocation — which is the whole reason to use `wt` instead of raw git. Done when the hooks have finished and the worktree path is captured — `wt list --format json` maps each `branch` to its `path`.
3. **Attach a workspace.** `herdr workspace create --cwd <worktree-path> --label <branch> --no-focus`. A separate workspace, rather than a split of the current pane, is what lets herdr's `branch` sidebar token tell the new work apart from everything else. Done when the reply yields both the new `workspace_id` and its `pane_id`.
4. **Start and hand off.** `herdr agent start <name> --kind claude --pane <pane_id>`, then `herdr agent prompt <name> "<task>" --wait --until working --timeout 15000`. See the `spawn-pane` skill for the start/prompt mechanics and their failure modes. Done when the reply is `agent_prompted` with `agent_status: working`.
5. **Collect.** Follow `spawn-pane`'s wait/read pattern — `herdr agent wait <name> --until idle --until done --until blocked`, then `herdr agent read <name>`. Done when what the agent produced, not just its finished state, is relayed back to the user.

## Context

How much context to hand over is the caller's call at invocation time, not fixed here. Default is self-contained but minimal: the repo, the worktree path, the branch, the task, the deliverable, and whether the agent may modify code. Never paste a raw transcript — the new agent inherits the old one's dead ends along with its findings.

## Traps

- **Never use `herdr worktree create`.** It looks like the obvious shortcut and it is the wrong tool: it drives raw git and skips worktrunk's pre-start hooks entirely. In any project whose worktrees need setup — virtualenv, env files, installed dependencies, allocated ports — a herdr-created worktree is a broken worktree. `wt` creates; herdr only attaches.
- **Confirm the name before creating.** Renaming a worktree after the fact means tearing it down and re-running every hook. A worktree name is expensive to change.
- **`wt switch` only moves the shell that ran it.** A non-interactive invocation creates the worktree and runs the hooks, but leaves the calling agent where it was. Pass the captured path to `herdr workspace create --cwd` explicitly; never assume the agent's own cwd followed.
- **Two id spaces.** `herdr agent …` subcommands target the agent *name*; `herdr pane …` and `herdr workspace …` subcommands target *ids*.
- **Parse the JSON.** Every herdr command returns a structured reply — read the fields for the ids and the status instead of treating a zero exit code as success.
- **Don't duplicate `spawn-pane`.** Agent start, prompt, stall recovery, and collection live there; this skill only adds the worktree and workspace in front of them.
