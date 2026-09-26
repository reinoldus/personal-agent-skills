"""`agent-swizzle <project> artifact-store`: upload, list, fetch, and share artifacts on S3-compatible storage."""

import textwrap
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

import boto3
import click
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from agent_swizzle import config as cfg

SECTION = "artifact-store"

# SigV4 presigned URLs are capped at 7 days.
MAX_EXPIRY = click.IntRange(1, 604800)


@dataclass
class StoreConfig:
    endpoint_url: str
    region: str
    bucket: str
    prefix: str
    access_key_id: str
    secret_access_key: str


def _client(conf: StoreConfig):
    return boto3.client(
        "s3",
        endpoint_url=conf.endpoint_url or None,
        region_name=conf.region or None,
        aws_access_key_id=conf.access_key_id,
        aws_secret_access_key=conf.secret_access_key,
        # Custom endpoints (MinIO, R2, Hetzner, ...) mostly need path-style addressing.
        config=BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path" if conf.endpoint_url else "auto"},
        ),
    )


def _project() -> str:
    return click.get_current_context().obj


def _require_config() -> StoreConfig:
    project = _project()
    if project not in cfg.list_projects():
        known = ", ".join(cfg.list_projects()) or "none"
        raise click.ClickException(
            f"Unknown project {project!r} (known: {known}). "
            f"Create it with `agent-swizzle {project} artifact-store setup`."
        )
    section = cfg.load_section(project, SECTION)
    if section is None:
        raise click.ClickException(
            f"artifact-store is not set up for {project!r}. Run `agent-swizzle {project} artifact-store setup` first."
        )
    return StoreConfig(**{field: section.get(field, "") for field in StoreConfig.__dataclass_fields__})


def _full_key(conf: StoreConfig, key: str) -> str:
    prefix = conf.prefix.strip("/")
    key = key.lstrip("/")
    return f"{prefix}/{key}" if prefix else key


def _relative_key(conf: StoreConfig, full_key: str) -> str:
    prefix = conf.prefix.strip("/")
    return full_key[len(prefix) + 1 :] if prefix and full_key.startswith(prefix + "/") else full_key


def _exists(client, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


@click.group(name="artifact-store")
def artifact_store():
    """Upload, list, fetch, and share artifacts on S3-compatible storage.

    Keys are relative to the configured prefix.
    """


ENDPOINT_HELP = """\
The S3 API address of your storage provider, WITHOUT the bucket name.
Leave blank for Amazon S3. Examples:
  DigitalOcean Spaces   https://nyc3.digitaloceanspaces.com
  Cloudflare R2         https://<account-id>.r2.cloudflarestorage.com
  Hetzner               https://fsn1.your-objectstorage.com
  Backblaze B2          https://s3.us-west-004.backblazeb2.com
  MinIO (local)         http://localhost:9000"""

BUCKET_HELP = """\
The bucket name. DigitalOcean calls it a "Space"; for the URL
https://my-space.nyc3.digitaloceanspaces.com it is `my-space`."""

REGION_HELP = """\
The region the bucket lives in: `nyc3` on DigitalOcean nyc3, `auto` on R2,
`eu-central-1` on AWS Frankfurt. The default is guessed from the endpoint;
us-east-1 works on most providers when unsure."""

PREFIX_HELP = """\
The folder inside the bucket that this project uses, e.g. `acme` or
`agents/acme`. Everything is stored below it, and the agent never sees keys
outside it. Leave blank to use the bucket root."""

KEY_ID_HELP = """\
An access key for the bucket. Create one at your provider:
  DigitalOcean  API -> Spaces Keys
  Cloudflare    R2 -> Manage API tokens
  AWS           IAM -> Users -> Security credentials
Prefer a key that can reach only this bucket: the agent can read everything it can."""

SECRET_HELP = """\
The secret that belongs to the access key; providers show it only once.
Your input stays hidden and is stored only in the local config file."""


def _guess_region(endpoint_url: str) -> str:
    host = urlparse(endpoint_url).hostname or ""
    parts = host.split(".")
    if host.endswith(".r2.cloudflarestorage.com"):
        return "auto"
    if len(parts) >= 3 and host.endswith((".digitaloceanspaces.com", ".your-objectstorage.com", ".backblazeb2.com")):
        return parts[-3]
    if len(parts) >= 4 and host.endswith(".amazonaws.com") and parts[-3] != "s3":
        return parts[-3]
    return "us-east-1"


def _normalize_endpoint(endpoint_url: str, bucket: str) -> str:
    """Add a missing scheme and drop a bucket name pasted in front of the host."""
    endpoint_url = endpoint_url.strip().rstrip("/")
    if endpoint_url and "://" not in endpoint_url:
        endpoint_url = f"https://{endpoint_url}"
        click.echo(f"Note: added the missing scheme: {endpoint_url}")
    parsed = urlparse(endpoint_url)
    if bucket and parsed.hostname and parsed.hostname.startswith(f"{bucket}."):
        endpoint_url = parsed._replace(netloc=parsed.netloc.removeprefix(f"{bucket}.")).geturl()
        click.echo(f"Note: removed the bucket name from the endpoint: {endpoint_url}")
    return endpoint_url


def _ask(value, title: str, help_text: str, default: str | None = None, **prompt_kwargs) -> str:
    if value is not None:
        return value
    click.echo()
    click.secho(title, bold=True)
    click.echo(textwrap.indent(help_text, "  "))
    return click.prompt("  >", default=default, show_default=bool(default), **prompt_kwargs)


@artifact_store.command()
@click.option("--endpoint-url", help="S3 API URL without the bucket name; empty for AWS S3.")
@click.option("--bucket", help="Bucket (DigitalOcean: Space) name.")
@click.option("--region", help="Bucket region; guessed from the endpoint when prompted.")
@click.option("--prefix", help="Folder inside the bucket for this project; empty for the bucket root.")
@click.option("--access-key-id", envvar="AGENT_SWIZZLE_S3_ACCESS_KEY_ID", help="Access key ID.")
@click.option(
    "--secret-access-key",
    envvar="AGENT_SWIZZLE_S3_SECRET_ACCESS_KEY",
    help="Prefer the prompt or the env var; a flag value lands in shell history.",
)
@click.option("--skip-check", is_flag=True, help="Save without testing the connection.")
def setup(endpoint_url, bucket, region, prefix, access_key_id, secret_access_key, skip_check):
    """Connect this project to a bucket; creates the project if needed.

    Prompts for every value not given as a flag and explains what goes where.
    Re-running it offers the saved values as defaults.
    """
    project = _project()
    saved = cfg.load_section(project, SECTION) or {}
    if None in (endpoint_url, bucket, region, prefix, access_key_id, secret_access_key):
        verb = "Updating" if saved else "Setting up"
        click.echo(f"{verb} artifact-store for project {project!r}.")
        click.echo(f"Config file: {cfg.project_path(project)} (only you can read it).")
        click.echo("Press Enter to accept the value in [brackets].")

    endpoint_url = _ask(endpoint_url, "1/6 Endpoint URL", ENDPOINT_HELP, saved.get("endpoint_url", ""))
    bucket = _ask(bucket, "2/6 Bucket", BUCKET_HELP, saved.get("bucket")).strip()
    endpoint_url = _normalize_endpoint(endpoint_url, bucket)
    region = _ask(region, "3/6 Region", REGION_HELP, saved.get("region") or _guess_region(endpoint_url))
    prefix = _ask(prefix, "4/6 Key prefix", PREFIX_HELP, saved.get("prefix", project))
    access_key_id = _ask(access_key_id, "5/6 Access key ID", KEY_ID_HELP, saved.get("access_key_id"))
    if secret_access_key is None and saved.get("secret_access_key"):
        secret_access_key = _ask(
            None, "6/6 Secret access key", SECRET_HELP + "\nLeave blank to keep the saved secret.", "", hide_input=True
        ) or saved["secret_access_key"]
    secret_access_key = _ask(secret_access_key, "6/6 Secret access key", SECRET_HELP, hide_input=True)

    conf = StoreConfig(
        endpoint_url=endpoint_url,
        region=region.strip(),
        bucket=bucket,
        prefix=prefix.strip().strip("/"),
        access_key_id=access_key_id.strip(),
        secret_access_key=secret_access_key.strip(),
    )
    click.echo()
    if not skip_check:
        try:
            client = _client(conf)
            client.list_objects_v2(Bucket=conf.bucket, Prefix=_full_key(conf, ""), MaxKeys=1)
        except (ClientError, BotoCoreError, ValueError) as exc:
            raise click.ClickException(f"Connection check failed, nothing saved: {exc}")
        click.echo("Connection check passed.")
    path = cfg.save_section(project, SECTION, asdict(conf))
    click.echo(f"Saved config to {path} (mode 600).")
    click.echo(f"Try it: agent-swizzle {project} artifact-store ls")


@artifact_store.command()
def status():
    """Show the active config with the secret redacted."""
    conf = _require_config()
    click.echo(f"project:       {_project()}")
    click.echo(f"config:        {cfg.project_path(_project())}")
    click.echo(f"endpoint_url:  {conf.endpoint_url or '(AWS default)'}")
    click.echo(f"region:        {conf.region}")
    click.echo(f"bucket:        {conf.bucket}")
    click.echo(f"prefix:        {conf.prefix or '(none)'}")
    click.echo(f"access_key_id: {conf.access_key_id[:4]}…")
    click.echo("secret:        (redacted)")


@artifact_store.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--key", help="Destination key. Defaults to the file name.")
@click.option("--force", is_flag=True, help="Overwrite an existing object.")
@click.option("--url", "with_url", is_flag=True, help="Also print a presigned download URL.")
@click.option("--expires", default=3600, show_default=True, type=MAX_EXPIRY, help="Presigned URL lifetime in seconds.")
def put(file, key, force, with_url, expires):
    """Upload FILE."""
    conf = _require_config()
    client = _client(conf)
    full_key = _full_key(conf, key or file.name)
    if not force and _exists(client, conf.bucket, full_key):
        raise click.ClickException(f"{_relative_key(conf, full_key)} already exists. Pass --force to overwrite.")
    client.upload_file(str(file), conf.bucket, full_key)
    click.echo(_relative_key(conf, full_key))
    if with_url:
        click.echo(_presign(client, conf, full_key, expires))


@artifact_store.command()
@click.argument("key")
@click.argument("dest", required=False)
@click.option("--force", is_flag=True, help="Overwrite an existing local file.")
def get(key, dest, force):
    """Download KEY to DEST.

    DEST defaults to the key's base name in the current directory. A DEST that
    ends in "/" or is an existing directory receives the file under its base name.
    """
    conf = _require_config()
    client = _client(conf)
    name = key.rstrip("/").rsplit("/", 1)[-1]
    if dest is None:
        target = Path(name)
    elif dest.endswith(("/", "\\")) or Path(dest).is_dir():
        target = Path(dest) / name
    else:
        target = Path(dest)
    if target.exists() and not force:
        raise click.ClickException(f"{target} already exists. Pass --force to overwrite.")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        client.download_file(conf.bucket, _full_key(conf, key), str(target))
    except (ClientError, OSError) as exc:
        raise click.ClickException(f"Download of {key} failed: {exc}")
    click.echo(str(target))


@artifact_store.command(name="ls")
@click.argument("prefix", default="")
@click.option("--long", "-l", "long_format", is_flag=True, help="Show size and modified time.")
def list_objects(prefix, long_format):
    """List keys under PREFIX."""
    conf = _require_config()
    client = _client(conf)
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=conf.bucket, Prefix=_full_key(conf, prefix)):
        for obj in page.get("Contents", []):
            rel = _relative_key(conf, obj["Key"])
            if long_format:
                click.echo(f"{obj['Size']:>12}  {obj['LastModified']:%Y-%m-%d %H:%M}  {rel}")
            else:
                click.echo(rel)


@artifact_store.command()
@click.argument("key")
@click.option("--expires", default=3600, show_default=True, type=MAX_EXPIRY, help="Lifetime in seconds (max 7 days).")
def url(key, expires):
    """Print a time-limited presigned download URL for KEY."""
    conf = _require_config()
    client = _client(conf)
    full_key = _full_key(conf, key)
    if not _exists(client, conf.bucket, full_key):
        raise click.ClickException(f"{key} does not exist.")
    click.echo(_presign(client, conf, full_key, expires))


def _presign(client, conf: StoreConfig, full_key: str, expires: int) -> str:
    return client.generate_presigned_url(
        "get_object", Params={"Bucket": conf.bucket, "Key": full_key}, ExpiresIn=expires
    )
