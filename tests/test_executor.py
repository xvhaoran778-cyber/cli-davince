from pathlib import Path

import pytest

from cli_anything.resolve.errors import ExitCode, ResolveCLIError
from cli_anything.resolve.plan import EditPlan, PlanExecutor, TimePosition
from cli_anything.resolve.services import ResolveService

from .fakes import fake_client


def make_plan(media_path: Path):
    return EditPlan.model_validate({
        "version": 1,
        "project": {"name": "Demo", "settings": {"frame_rate": 25, "width": 1920, "height": 1080}},
        "timeline": {"name": "Main"},
        "media": [{"id": "clip", "path": str(media_path)}],
        "edits": [{"media": "clip", "source_in": {"seconds": 1}, "source_out": {"seconds": 2}, "properties": {"ZoomX": 1.2}}],
    })


def test_plan_executor_success(tmp_path):
    media = tmp_path / "clip.mp4"; media.write_bytes(b"fake")
    client, _ = fake_client()
    result = PlanExecutor(ResolveService(client)).apply(make_plan(media))
    assert result["applied"] is True
    assert [step["step"] for step in result["completed_steps"]][-1] == "project.save"


def test_plan_uses_media_fps_for_source_and_timeline_fps_for_record_position(tmp_path):
    media = tmp_path / "clip.mp4"; media.write_bytes(b"fake")
    client, resolve = fake_client()
    plan = make_plan(media)
    plan.edits[0].record_at = TimePosition(seconds=3)
    PlanExecutor(ResolveService(client)).apply(plan)
    info = resolve.manager.current.pool.last_append[0]
    assert info["startFrame"] == 50
    assert info["endFrame"] == 99
    assert info["recordFrame"] == 90075


def test_plan_executor_reports_completed_steps_on_failure(tmp_path):
    media = tmp_path / "clip.mp4"; media.write_bytes(b"fake")
    client, _ = fake_client()
    service = ResolveService(client)
    service.clip_append = lambda *args, **kwargs: (_ for _ in ()).throw(ResolveCLIError("append failed"))
    with pytest.raises(ResolveCLIError) as error:
        PlanExecutor(service).apply(make_plan(media))
    assert error.value.exit_code == ExitCode.PARTIAL_FAILURE
    assert error.value.details["completed_steps"]
