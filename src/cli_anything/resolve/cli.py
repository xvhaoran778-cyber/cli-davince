from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path
from typing import Any

import click
from pydantic import ValidationError

from .errors import ExitCode, ResolveCLIError, ValidationFailure
from .output import emit, emit_error
from .plan import EditPlan, PlanExecutor, load_plan, validate_plan
from .resolve_client import ResolveClient
from .services import ResolveService


class Context:
    def __init__(self, json_output: bool, client: ResolveClient | None = None) -> None:
        self.json_output = json_output
        self.client = client or ResolveClient()
        self.service = ResolveService(self.client)


pass_context = click.make_pass_decorator(Context)


def json_value(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        result = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValidationFailure("Expected a JSON object", details=str(exc)) from exc
    if not isinstance(result, dict):
        raise ValidationFailure("Expected a JSON object")
    return result


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
@click.version_option(package_name="cli-anything-resolve")
@click.pass_context
def cli(ctx: click.Context, json_output: bool) -> None:
    """Control a running DaVinci Resolve instance from the command line."""
    if ctx.obj is None:
        ctx.obj = Context(json_output)


@cli.command()
@pass_context
def doctor(ctx: Context) -> None:
    """Check the SDK, Python runtime, Resolve process, and scripting connection."""
    data = ctx.client.doctor()
    emit(data, json_output=ctx.json_output)
    if not data["healthy"]:
        raise click.exceptions.Exit(ExitCode.BACKEND_UNAVAILABLE)


@cli.command()
@pass_context
def status(ctx: Context) -> None:
    """Show the active Resolve, project, timeline, and render state."""
    emit(ctx.service.status(), json_output=ctx.json_output)


@cli.command()
@pass_context
def repl(ctx: Context) -> None:
    """Start a small interactive command loop using the same CLI commands."""
    click.echo("DaVinci Resolve CLI. Type 'help' or 'exit'.")
    while True:
        try:
            line = click.prompt("resolve", prompt_suffix="> ", default="", show_default=False)
        except (EOFError, KeyboardInterrupt):
            click.echo()
            return
        if not line.strip():
            continue
        if line.strip() in {"exit", "quit"}:
            return
        args = ["--json"] if ctx.json_output else []
        args.extend(["--help"] if line.strip() == "help" else shlex.split(line))
        try:
            cli.main(args=args, prog_name="cli-anything-resolve", standalone_mode=False, obj=ctx)
        except ResolveCLIError as exc:
            emit_error(exc, json_output=ctx.json_output)
        except click.ClickException as exc:
            exc.show()


@cli.group()
def project() -> None:
    """Manage Resolve projects."""


@project.command("list")
@pass_context
def project_list(ctx: Context) -> None:
    emit(ctx.service.project_list(), json_output=ctx.json_output)


@project.command("create")
@click.argument("name")
@click.option("--frame-rate", type=float, default=24, show_default=True)
@click.option("--width", type=int, default=1920, show_default=True)
@click.option("--height", type=int, default=1080, show_default=True)
@pass_context
def project_create(ctx: Context, name: str, frame_rate: float, width: int, height: int) -> None:
    result = ctx.service.project_create(name, {"frame_rate": frame_rate, "width": width, "height": height})
    emit(result, json_output=ctx.json_output, message=f"Created project {name}")


@project.command("open")
@click.argument("name")
@pass_context
def project_open(ctx: Context, name: str) -> None:
    emit(ctx.service.project_open(name), json_output=ctx.json_output, message=f"Opened project {name}")


@project.command("current")
@pass_context
def project_current(ctx: Context) -> None:
    emit(ctx.service.project_info(), json_output=ctx.json_output)


@project.command("save")
@pass_context
def project_save(ctx: Context) -> None:
    emit(ctx.service.project_save(), json_output=ctx.json_output, message="Project saved")


@cli.group()
def media() -> None:
    """Inspect and import Media Pool items."""


@media.command("list")
@pass_context
def media_list(ctx: Context) -> None:
    emit(ctx.service.media_list(), json_output=ctx.json_output)


@media.command("import")
@click.argument("paths", nargs=-1, required=True, type=click.Path(path_type=Path))
@pass_context
def media_import(ctx: Context, paths: tuple[Path, ...]) -> None:
    result = ctx.service.media_import(list(paths))
    emit(result, json_output=ctx.json_output, message=f"Imported {len(result)} media item(s)")


@cli.group()
def timeline() -> None:
    """Manage timelines."""


@timeline.command("list")
@pass_context
def timeline_list(ctx: Context) -> None:
    emit(ctx.service.timeline_list(), json_output=ctx.json_output)


@timeline.command("inspect")
@click.argument("identity", required=False)
@pass_context
def timeline_inspect(ctx: Context, identity: str | None) -> None:
    emit(ctx.service.timeline_inspect(identity), json_output=ctx.json_output)


@timeline.command("create")
@click.argument("name")
@click.option("--replace", is_flag=True, help="Delete and recreate an existing timeline with the same name.")
@pass_context
def timeline_create(ctx: Context, name: str, replace: bool) -> None:
    emit(ctx.service.timeline_create(name, replace), json_output=ctx.json_output, message=f"Created timeline {name}")


@timeline.command("delete")
@click.argument("identity")
@click.option("--yes", is_flag=True, help="Confirm timeline deletion.")
@pass_context
def timeline_delete(ctx: Context, identity: str, yes: bool) -> None:
    if not yes:
        raise ValidationFailure("Timeline deletion requires --yes")
    emit(ctx.service.timeline_delete(identity), json_output=ctx.json_output, message=f"Deleted timeline {identity}")


@cli.group()
def clip() -> None:
    """Edit clips on the current timeline."""


@clip.command("append")
@click.argument("media_identity")
@click.option("--source-in", type=int)
@click.option("--source-out", type=int, help="Exclusive source end frame.")
@click.option("--track", type=click.IntRange(min=1), default=1, show_default=True)
@click.option("--record-at", type=int)
@click.option("--media-type", type=click.Choice(["all", "video", "audio"]), default="all")
@click.option("--properties", help="JSON object of Resolve TimelineItem properties.")
@pass_context
def clip_append(
    ctx: Context,
    media_identity: str,
    source_in: int | None,
    source_out: int | None,
    track: int,
    record_at: int | None,
    media_type: str,
    properties: str | None,
) -> None:
    result = ctx.service.clip_append(
        media_identity,
        source_in=source_in,
        source_out=source_out,
        track=track,
        record_at=record_at,
        media_type=media_type,
        properties=json_object(properties),
    )
    emit(result, json_output=ctx.json_output, message=f"Appended {len(result)} timeline item(s)")


@clip.command("delete")
@click.argument("identity")
@click.option("--ripple", is_flag=True)
@click.option("--yes", is_flag=True)
@pass_context
def clip_delete(ctx: Context, identity: str, ripple: bool, yes: bool) -> None:
    if not yes:
        raise ValidationFailure("Clip deletion requires --yes")
    emit(ctx.service.clip_delete(identity, ripple), json_output=ctx.json_output, message=f"Deleted clip {identity}")


@clip.command("set-property")
@click.argument("identity")
@click.argument("key")
@click.argument("value")
@pass_context
def clip_set_property(ctx: Context, identity: str, key: str, value: str) -> None:
    emit(ctx.service.clip_set_property(identity, key, json_value(value)), json_output=ctx.json_output)


@cli.group()
def caption() -> None:
    """Create and manage captions."""


@caption.command("auto")
@click.option("--settings", help="JSON object accepted by Resolve CreateSubtitlesFromAudio.")
@pass_context
def caption_auto(ctx: Context, settings: str | None) -> None:
    emit(ctx.service.caption_auto(json_object(settings)), json_output=ctx.json_output, message="Automatic captioning started")


@cli.group()
def render() -> None:
    """Configure and monitor rendering."""


@render.command("presets")
@pass_context
def render_presets(ctx: Context) -> None:
    emit(ctx.service.render_presets(), json_output=ctx.json_output)


@render.command("formats")
@pass_context
def render_formats(ctx: Context) -> None:
    emit(ctx.service.render_formats(), json_output=ctx.json_output)


@render.command("start")
@click.option("--preset")
@click.option("--target-dir", required=True, type=click.Path(path_type=Path))
@click.option("--name", required=True)
@click.option("--wait/--no-wait", default=False)
@click.option("--timeout", type=float)
@pass_context
def render_start(ctx: Context, preset: str | None, target_dir: Path, name: str, wait: bool, timeout: float | None) -> None:
    emit(
        ctx.service.render_start(preset=preset, target_dir=target_dir, name=name, wait=wait, timeout=timeout),
        json_output=ctx.json_output,
        message="Render started",
    )


@render.command("status")
@click.argument("job_id", required=False)
@pass_context
def render_status(ctx: Context, job_id: str | None) -> None:
    emit(ctx.service.render_status(job_id), json_output=ctx.json_output)


@render.command("wait")
@click.argument("job_id")
@click.option("--timeout", type=float)
@pass_context
def render_wait(ctx: Context, job_id: str, timeout: float | None) -> None:
    emit(ctx.service.render_wait(job_id, timeout=timeout), json_output=ctx.json_output)


@cli.group("plan")
def plan_group() -> None:
    """Validate and apply declarative edit plans."""


@plan_group.command("validate")
@click.argument("path", type=click.Path(path_type=Path))
@click.option("--no-check-files", is_flag=True)
@pass_context
def plan_validate(ctx: Context, path: Path, no_check_files: bool) -> None:
    plan = load_plan(path)
    emit(validate_plan(plan, check_files=not no_check_files), json_output=ctx.json_output, message="Plan is valid")


@plan_group.command("apply")
@click.argument("path", type=click.Path(path_type=Path))
@pass_context
def plan_apply(ctx: Context, path: Path) -> None:
    plan = load_plan(path)
    emit(PlanExecutor(ctx.service).apply(plan), json_output=ctx.json_output, message="Plan applied")


def main() -> None:
    json_output = "--json" in sys.argv
    try:
        result = cli.main(standalone_mode=False)
        if isinstance(result, int) and result:
            raise SystemExit(result)
    except ResolveCLIError as exc:
        emit_error(exc, json_output=json_output)
        raise SystemExit(int(exc.exit_code)) from exc
    except (ValidationError, json.JSONDecodeError) as exc:
        error = ValidationFailure("Invalid input", details=str(exc))
        emit_error(error, json_output=json_output)
        raise SystemExit(int(error.exit_code)) from exc
    except click.ClickException as exc:
        if json_output:
            emit_error(ValidationFailure(exc.format_message()), json_output=True)
        else:
            exc.show()
        raise SystemExit(exc.exit_code) from exc


if __name__ == "__main__":
    main()
