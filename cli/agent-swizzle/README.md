# agent-swizzle

Pocket knife of small CLI tools for coding agents. Each tool is one subcommand, and each has a matching skill in [`skills/`](../../skills).

## Install

```bash
uv tool install "git+https://github.com/reinoldus/personal-agent-skills#subdirectory=cli/agent-swizzle"
```

Upgrade later with `uv tool upgrade agent-swizzle`.

## Projects

Every call names a project first:

```bash
agent-swizzle <project> <tool> <command> ...
```

Each project has its own config, so `acme` and `globex` can use different buckets and different keys. Run `agent-swizzle` without arguments to list the configured projects. A tool's `setup` creates the project if it does not exist yet. Project names use lowercase letters, digits, `-`, and `_`.

## Config

One file per project: `~/.config/agent-swizzle/projects/<project>.toml`, with one TOML table per tool and mode `600`. Set `AGENT_SWIZZLE_CONFIG_DIR` to use a different directory. A tool's `setup` rewrites only that tool's table.

## Tools

### `artifact-store`

Upload, list, download, and share files on S3-compatible storage. Skill: [`artifact-store`](../../skills/artifact-store/SKILL.md).

| Command | What it does |
| --- | --- |
| `agent-swizzle <project> artifact-store setup` | Store the connection for this project. Tests it before it saves anything. |
| `agent-swizzle <project> artifact-store status` | Show the active config, secret redacted. |
| `agent-swizzle <project> artifact-store put FILE [--key K] [--force] [--url]` | Upload a file. Refuses to overwrite unless `--force`. |
| `agent-swizzle <project> artifact-store ls [PREFIX] [-l]` | List keys. |
| `agent-swizzle <project> artifact-store get KEY [DEST] [--force]` | Download a key. |
| `agent-swizzle <project> artifact-store url KEY [--expires SECONDS]` | Print a presigned download URL (default 1 h, max 7 days). |

All keys are relative to the configured prefix. A presigned URL is the S3 counterpart of an Azure SAS token: a signed, time-limited link to one object. Anyone who has the link can download the object until it expires, without credentials.

#### Setup examples

`setup` prompts for each value, and the secret input is hidden. The **endpoint URL never contains the bucket name**: the bucket goes in its own prompt. Use a key that can reach **only this bucket**. The agent can read everything the key can read.

| Provider | Endpoint URL | Region | Bucket |
| --- | --- | --- | --- |
| DigitalOcean Spaces | `https://nyc3.digitaloceanspaces.com` | `nyc3` | `my-space` |
| Cloudflare R2 | `https://<account-id>.r2.cloudflarestorage.com` | `auto` | `my-bucket` |
| AWS S3 | *(blank)* | `eu-central-1` | `my-bucket` |
| Hetzner Object Storage | `https://fsn1.your-objectstorage.com` | `fsn1` | `my-bucket` |
| Backblaze B2 | `https://s3.us-west-004.backblazeb2.com` | `us-west-004` | `my-bucket` |
| MinIO (local) | `http://localhost:9000` | `us-east-1` | `my-bucket` |

Replace the region part of the endpoint (`nyc3`, `fsn1`, ...) with your own region.

A DigitalOcean Space called `my-space` in `nyc3`, set up for the project `acme`:

```console
$ agent-swizzle acme artifact-store setup
Endpoint URL (blank for AWS S3): https://nyc3.digitaloceanspaces.com
Region [us-east-1]: nyc3
Bucket: my-space
Key prefix inside the bucket (blank for none): agents
Access key ID: <spaces access key>
Secret access key: <hidden>
Connection check passed.
Saved config to ~/.config/agent-swizzle/projects/acme.toml (mode 600).
```

Common mistake: the DigitalOcean UI shows the Space URL `https://my-space.nyc3.digitaloceanspaces.com`. Do not paste that one. Remove the `my-space.` part.

The same setup without prompts, for example in a script (the secret still comes from the env var, not a flag):

```bash
AGENT_SWIZZLE_S3_SECRET_ACCESS_KEY=... agent-swizzle globex artifact-store setup \
  --endpoint-url https://nyc3.digitaloceanspaces.com --region nyc3 \
  --bucket globex-artifacts --prefix "" --access-key-id <key-id>
```

Usage afterwards:

```bash
agent-swizzle                                               # list projects
agent-swizzle acme artifact-store put report.md --key 2026-09-26/report.md --url
agent-swizzle acme artifact-store ls 2026-09-26/
agent-swizzle acme artifact-store get 2026-09-26/report.md ./downloads/
```

## Develop

```bash
uv sync
uv run pytest
```

To add a tool: create `src/agent_swizzle/<tool>.py` with a click group, register it in `cli.py`, read the project with `click.get_current_context().obj`, keep the tool's config in its own table via `config.load_section` / `config.save_section`, and add a skill under `skills/<tool>/`.
