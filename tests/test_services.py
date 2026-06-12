from pathlib import Path

import pytest

from cli_anything.resolve.errors import Conflict
from cli_anything.resolve.services import ResolveService

from .fakes import fake_client


def configured_service(tmp_path):
    client, resolve = fake_client()
    service = ResolveService(client)
    service.project_create("Demo", {"frame_rate": 25, "width": 1920, "height": 1080})
    service.timeline_create("Main")
    media_path = tmp_path / "clip.mp4"
    media_path.write_bytes(b"fake")
    media = service.media_import([media_path])[0]
    return service, resolve, media


def test_timeline_conflict_and_explicit_replace(tmp_path):
    service, _, _ = configured_service(tmp_path)
    with pytest.raises(Conflict):
        service.timeline_create("Main")
    result = service.timeline_create("Main", replace=True)
    assert result["replaced"] is True


def test_append_converts_exclusive_end_and_sets_properties(tmp_path):
    service, resolve, media = configured_service(tmp_path)
    added = service.clip_append(media["id"], source_in=10, source_out=20, properties={"ZoomX": 1.1})
    info = resolve.manager.current.pool.last_append[0]
    assert info["startFrame"] == 10
    assert info["endFrame"] == 19
    assert added[0]["duration"] == 10
    assert added[0]["properties"]["ZoomX"] == 1.1


def test_render_round_trip(tmp_path):
    service, _, _ = configured_service(tmp_path)
    result = service.render_start(preset="YouTube 1080p", target_dir=tmp_path / "out", name="demo", wait=True)
    assert result["status"]["JobStatus"] == "Complete"


def test_render_wait_accepts_localized_complete_status(tmp_path):
    service, resolve, _ = configured_service(tmp_path)
    resolve.manager.current.jobs["localized"] = {"JobStatus": "完成", "CompletionPercentage": 100}
    assert service.render_wait("localized", timeout=0.1)["JobStatus"] == "完成"
