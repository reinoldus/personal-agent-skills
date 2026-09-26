# personal-agent-skills

Personal agent skills, installable with the [skills CLI](https://github.com/vercel-labs/skills):

```bash
npx skills add reinoldus/personal-agent-skills
```

## Skills

- **spawn-pane** — spawn a herdr pane running a fresh coding agent and hand a task off to it.
- **spawn-worktree** — create a git worktree with `wt`, open it as its own herdr workspace running a fresh agent, and hand a task off to it.
- **artifact-store** — upload, list, download, and share files on S3-compatible storage with `agent-swizzle <project> artifact-store`; each project has its own bucket.

## CLIs

- **[agent-swizzle](cli/agent-swizzle/README.md)** — pocket knife of small tools for agents; every call names a project (`agent-swizzle <project> <tool> ...`), and each tool has a matching skill. Install with `uv tool install "git+https://github.com/reinoldus/personal-agent-skills#subdirectory=cli/agent-swizzle"`.
