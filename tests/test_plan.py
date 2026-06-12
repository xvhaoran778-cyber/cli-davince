from pathlib import Path

import pytest

from cli_anything.resolve.errors import ValidationFailure
from cli_anything.resolve.plan import EditPlan, TimePosition, position_to_frames, timecode_to_frames, validate_plan


def test_position_conversions():
    assert position_to_frames(TimePosition(seconds=2.0), 25) == 50
    assert position_to_frames(TimePosition(frames=12), 25) == 12
    assert timecode_to_frames("01:00:00:00", 25) == 90000


def test_time_position_requires_exactly_one_value():
    with pytest.raises(Exception):
        TimePosition(frames=1, seconds=1)


def test_plan_rejects_missing_media_and_bad_range(tmp_path):
    missing = tmp_path / "missing.mp4"
    plan = EditPlan.model_validate({
        "version": 1,
        "project": {"name": "Demo", "settings": {"frame_rate": 25, "width": 1920, "height": 1080}},
        "timeline": {"name": "Main"},
        "media": [{"id": "a", "path": str(missing)}],
        "edits": [{"media": "a", "source_in": {"frames": 20}, "source_out": {"frames": 10}}],
    })
    with pytest.raises(ValidationFailure) as error:
        validate_plan(plan)
    codes = {problem["code"] for problem in error.value.details}
    assert codes == {"media_not_found", "invalid_source_range"}

