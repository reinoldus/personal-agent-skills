"""Local config, one TOML file per project with one table per tool. Lives outside any repo, mode 0600."""

import os
import re
import tempfile
import tomllib
from pathlib import Path

import tomli_w

PROJECT_NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")


def config_dir() -> Path:
    if override := os.environ.get("AGENT_SWIZZLE_CONFIG_DIR"):
        return Path(override)
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "agent-swizzle"


def project_path(project: str) -> Path:
    return config_dir() / "projects" / f"{project}.toml"


def list_projects() -> list[str]:
    return sorted(path.stem for path in (config_dir() / "projects").glob("*.toml"))


def _load_all(project: str) -> dict[str, dict[str, str]]:
    path = project_path(project)
    return tomllib.loads(path.read_text()) if path.exists() else {}


def load_section(project: str, name: str) -> dict[str, str] | None:
    return _load_all(project).get(name)


def save_section(project: str, name: str, values: dict[str, str]) -> Path:
    data = _load_all(project)
    data[name] = values
    path = project_path(project)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # mkstemp creates the file 0600, so secrets are never readable by others; the
    # rename swaps it in atomically, so a crash never leaves a partial config.
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{project}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            tomli_w.dump(data, fh)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
    return path
