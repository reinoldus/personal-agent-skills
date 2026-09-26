"""agent-swizzle: pocket knife of small tools for coding agents. Each tool is one subcommand."""

import click

from agent_swizzle import config as cfg
from agent_swizzle.artifact_store import artifact_store


def _overview(ctx: click.Context) -> str:
    tools = "\n".join(
        f"  {name:<16}{command.get_short_help_str(limit=70)}" for name, command in sorted(ctx.command.commands.items())
    )
    projects = cfg.list_projects()
    project_lines = "\n".join(f"  {name}" for name in projects) or "  (none yet)"
    example = projects[0] if projects else "my-project"
    return f"""\
agent-swizzle - pocket knife of small tools for coding agents.

Each project (a client, a repo, ...) has its own settings, e.g. its own bucket
and access key, so an agent working on one project never touches another's data.

Usage:
  agent-swizzle <project> <tool> <command> [ARGS]

Tools:
{tools}

Projects ({cfg.config_dir() / "projects"}):
{project_lines}

Examples:
  agent-swizzle {example} artifact-store setup        connect a project to a bucket (creates it)
  agent-swizzle {example} artifact-store put report.md --url
  agent-swizzle {example} artifact-store ls

Details: agent-swizzle <project> <tool> --help"""


@click.group(invoke_without_command=True)
@click.argument("project", required=False)
@click.version_option(package_name="agent-swizzle")
@click.pass_context
def cli(ctx, project):
    """Pocket knife of small tools for coding agents.

    Every call names a PROJECT first; each project has its own settings.
    Run without arguments for an overview with the configured projects.
    A tool's `setup` creates the project if it does not exist yet.

    Usage: agent-swizzle <project> <tool> <command> [ARGS]
    """
    if project is None:
        click.echo(_overview(ctx))
        return
    if not cfg.PROJECT_NAME.fullmatch(project):
        raise click.BadParameter("use lowercase letters, digits, '-' and '_' (e.g. `my-project`).", param_hint="PROJECT")
    ctx.obj = project
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


cli.add_command(artifact_store)


def main():
    cli()
