---
name: artifact-store
description: Upload, list, download, and share files on the user's S3-compatible storage with `agent-swizzle <project> artifact-store`. Use when the user wants an artifact (report, build output, screenshot, dataset) stored off-machine, fetched back from storage, or shared as a time-limited download link.
---

# artifact-store

`agent-swizzle <project> artifact-store` moves files between this machine and the S3-compatible bucket configured for one project. Each project has its own bucket and credentials. All keys are relative to the project's configured prefix.

## Steps

1. **Pick the project.** Run `agent-swizzle` with no arguments; it lists the configured projects. Use the project the user named. Otherwise, pick the one that clearly matches the current repo or task. If none matches clearly, ask the user. Never guess between two candidates. Done when you have one project name.
2. **Check.** `agent-swizzle <project> artifact-store status`. Done when it prints the bucket. If it reports an unknown project or no artifact-store setup, stop and ask the user to run `! agent-swizzle <project> artifact-store setup` themselves. Never run setup for them and never ask them to paste the secret into the chat.
3. **Act.** Pick the command:
   - Upload: `agent-swizzle <project> artifact-store put <file> --key <key>`. Prints the stored key.
   - List: `agent-swizzle <project> artifact-store ls [<prefix>] [-l]`.
   - Download: `agent-swizzle <project> artifact-store get <key> [<dest>]`. Prints the local path.
   - Share: `agent-swizzle <project> artifact-store url <key> [--expires <seconds>]`, or `put ... --url` to upload and share in one step. Default lifetime is 3600 s, max 604800 s (7 days).
4. **Report.** Give the user the project, the key, and the URL if one was requested. Done when the user has the key or link.

## Rules

- **One project per task.** Do not copy files between projects unless the user asks. Each project's bucket can belong to a different client.
- **Choose explicit keys.** Group related files, e.g. `<YYYY-MM-DD>/<name>`. Without `--key`, the file name is the key and collides easily.
- **No silent overwrites.** `put` and `get` refuse to overwrite. Pass `--force` only when the user asked to replace the file.
- **Links are bearer tokens.** Anyone with a presigned URL can download the object until it expires. Use the shortest lifetime that works, and do not post links to public places unless the user asks.
- **Never expose the secret.** Do not read, print, or copy anything under `~/.config/agent-swizzle/`. Use `status`, which redacts the secret.
- **Missing CLI.** If `agent-swizzle` is not on PATH, tell the user to install it: `uv tool install "git+https://github.com/reinoldus/personal-agent-skills#subdirectory=cli/agent-swizzle"`.
