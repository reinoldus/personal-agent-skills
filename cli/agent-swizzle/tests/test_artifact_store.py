import os
import stat

import boto3
import pytest
from click.testing import CliRunner
from moto import mock_aws

from agent_swizzle import config as cfg
from agent_swizzle.cli import cli

# Dummy values for moto; never real credentials.
FAKE_KEY_ID = "testing"
FAKE_SECRET = "testing-secret"
BUCKET = "artifacts"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SWIZZLE_CONFIG_DIR", str(tmp_path / "config"))
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield tmp_path


PROJECT = "acme"


def invoke(*args, input=None):
    return CliRunner().invoke(cli, list(args), input=input, catch_exceptions=False)


def run(*args, input=None, project=PROJECT):
    return invoke(project, "artifact-store", *args, input=input)


def configure(project=PROJECT, bucket=BUCKET):
    return run(
        "setup",
        "--endpoint-url", "",
        "--region", "us-east-1",
        "--bucket", bucket,
        "--prefix", "agent",
        "--access-key-id", FAKE_KEY_ID,
        input=f"{FAKE_SECRET}\n",
        project=project,
    )


def test_commands_require_setup(env):
    result = run("ls")
    assert result.exit_code != 0
    assert "Unknown project 'acme'" in result.output
    assert "agent-swizzle acme artifact-store setup" in result.output


def test_no_project_lists_projects(env):
    overview = invoke().output
    assert "pocket knife" in overview and "artifact-store" in overview and "(none yet)" in overview
    configure("acme")
    configure("globex")
    overview = invoke().output
    assert "\n  acme\n  globex\n" in overview
    assert "agent-swizzle acme artifact-store setup" in overview


def test_rejects_bad_project_name(env):
    result = invoke("My Project", "artifact-store", "ls")
    assert result.exit_code != 0 and "my-project" in result.output


def test_projects_are_isolated(env):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="other")
    configure("acme")
    configure("globex", bucket="other")
    src = env / "a.txt"
    src.write_text("a")
    run("put", str(src), project="acme")
    assert run("ls", project="acme").output.split() == ["a.txt"]
    assert run("ls", project="globex").output.split() == []
    assert "bucket:        other" in run("status", project="globex").output


def test_setup_writes_private_config(env):
    result = configure()
    assert result.exit_code == 0, result.output
    path = env / "config" / "projects" / "acme.toml"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert FAKE_SECRET in path.read_text()
    assert FAKE_SECRET not in run("status").output


def test_setup_rejects_missing_bucket(env):
    result = run(
        "setup", "--endpoint-url", "", "--region", "us-east-1", "--bucket", "nope",
        "--prefix", "", "--access-key-id", FAKE_KEY_ID, input=f"{FAKE_SECRET}\n",
    )
    assert result.exit_code != 0
    assert not (env / "config" / "projects" / "acme.toml").exists()


def test_put_ls_get_url_roundtrip(env):
    configure()
    src = env / "report.md"
    src.write_text("hello")

    assert run("put", str(src), "--key", "runs/report.md").output.strip() == "runs/report.md"
    raw = boto3.client("s3", region_name="us-east-1").list_objects_v2(Bucket=BUCKET)
    assert [o["Key"] for o in raw["Contents"]] == ["agent/runs/report.md"]

    assert run("ls", "runs/").output.split() == ["runs/report.md"]

    dup = run("put", str(src), "--key", "runs/report.md")
    assert dup.exit_code != 0 and "--force" in dup.output
    assert run("put", str(src), "--key", "runs/report.md", "--force").exit_code == 0

    dest = env / "out"
    dest.mkdir()
    assert run("get", "runs/report.md", str(dest)).exit_code == 0
    assert (dest / "report.md").read_text() == "hello"

    link = run("url", "runs/report.md", "--expires", "60").output.strip()
    assert "agent/runs/report.md" in link and "X-Amz-Signature" in link
    assert run("url", "missing.md").exit_code != 0
    assert run("url", "runs/report.md", "--expires", "999999").exit_code != 0


def test_setup_keeps_other_sections(env):
    cfg.save_section(PROJECT, "other-tool", {"token": "x"})
    configure()
    assert cfg.load_section(PROJECT, "other-tool") == {"token": "x"}
    assert cfg.load_section(PROJECT, "artifact-store")["bucket"] == BUCKET


def test_setup_defaults_to_aws_compatible_region(env):
    result = run(
        "setup", "--endpoint-url", "", "--bucket", BUCKET, "--prefix", "",
        "--access-key-id", FAKE_KEY_ID, input=f"\n{FAKE_SECRET}\n",
    )
    assert result.exit_code == 0, result.output
    assert cfg.load_section(PROJECT, "artifact-store")["region"] == "us-east-1"


def test_setup_checks_prefix_with_trailing_slash(env, monkeypatch):
    from agent_swizzle import artifact_store

    seen = []
    real_client = artifact_store._client

    def spy(conf):
        client = real_client(conf)
        client.meta.events.register("before-parameter-build.s3.ListObjectsV2", lambda params, **_: seen.append(params["Prefix"]))
        return client

    monkeypatch.setattr(artifact_store, "_client", spy)
    configure()
    assert seen == ["agent/"]


def test_get_into_missing_directory(env):
    configure()
    src = env / "report.md"
    src.write_text("hello")
    run("put", str(src))
    dest = env / "downloads"
    assert run("get", "report.md", f"{dest}/").exit_code == 0
    assert (dest / "report.md").read_text() == "hello"
    assert run("get", "report.md", str(env / "a" / "b.md")).exit_code == 0
    assert (env / "a" / "b.md").read_text() == "hello"


def setup_skip_check(*extra, input=None):
    return run("setup", "--prefix", "", "--access-key-id", FAKE_KEY_ID, "--skip-check", *extra, input=input)


def test_setup_fixes_scheme_and_bucket_in_endpoint(env):
    result = setup_skip_check(
        "--endpoint-url", "my-space.nyc3.digitaloceanspaces.com", "--bucket", "my-space",
        input=f"\n{FAKE_SECRET}\n",
    )
    assert result.exit_code == 0, result.output
    saved = cfg.load_section(PROJECT, "artifact-store")
    assert saved["endpoint_url"] == "https://nyc3.digitaloceanspaces.com"
    assert saved["region"] == "nyc3"


def test_setup_explains_each_prompt_and_rerun_keeps_secret(env):
    first = run("setup", "--skip-check", input=f"\n{BUCKET}\n\n\n{FAKE_KEY_ID}\n{FAKE_SECRET}\n")
    assert first.exit_code == 0, first.output
    for title in ("1/6 Endpoint URL", "2/6 Bucket", "3/6 Region", "4/6 Key prefix", "5/6 Access key ID", "6/6 Secret"):
        assert title in first.output
    assert "Spaces Keys" in first.output
    assert FAKE_SECRET not in first.output
    saved = cfg.load_section(PROJECT, "artifact-store")
    assert saved["prefix"] == PROJECT and saved["region"] == "us-east-1"

    again = run("setup", "--skip-check", input="\n\n\n\n\n\n")
    assert again.exit_code == 0, again.output
    assert "Updating" in again.output
    assert cfg.load_section(PROJECT, "artifact-store") == saved


def test_config_roundtrips_awkward_values_and_tightens_mode(env):
    path = cfg.project_path(PROJECT)
    path.parent.mkdir(parents=True)
    path.write_text("")
    path.chmod(0o644)
    values = {"prefix": "emoji-😀-del-\x7f", "quote": 'a"b\\c'}
    cfg.save_section(PROJECT, "x", values)
    assert cfg.load_section(PROJECT, "x") == values
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert list(path.parent.glob("*.tmp")) == []
