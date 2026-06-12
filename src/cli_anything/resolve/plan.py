from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .errors import Conflict, ExitCode, ResolveCLIError, ValidationFailure
from .services import ResolveService


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TimePosition(StrictModel):
    frames: int | None = Field(default=None, ge=0)
    seconds: float | None = Field(default=None, ge=0)
    timecode: str | None = None

    @model_validator(mode="after")
    def exactly_one(self) -> "TimePosition":
        if sum(value is not None for value in (self.frames, self.seconds, self.timecode)) != 1:
            raise ValueError("exactly one of frames, seconds, or timecode is required")
        return self


class ProjectSettings(StrictModel):
    frame_rate: float = Field(default=24, gt=0)
    width: int = Field(default=1920, gt=0)
    height: int = Field(default=1080, gt=0)


class ProjectSpec(StrictModel):
    name: str = Field(min_length=1)
    create: bool = True
    settings: ProjectSettings = Field(default_factory=ProjectSettings)


class TimelineSpec(StrictModel):
    name: str = Field(min_length=1)
    replace: bool = False


class MediaSpec(StrictModel):
    id: str = Field(min_length=1)
    path: Path

    @field_validator("path")
    @classmethod
    def absolute_path(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("media path must be absolute")
        return value


class EditSpec(StrictModel):
    media: str
    source_in: TimePosition | None = None
    source_out: TimePosition | None = None
    track: int = Field(default=1, ge=1)
    record_at: TimePosition | None = None
    media_type: Literal["all", "video", "audio"] = "all"
    properties: dict[str, Any] = Field(default_factory=dict)


class CaptionSpec(StrictModel):
    auto: bool = False
    settings: dict[str, Any] = Field(default_factory=dict)


class RenderSpec(StrictModel):
    preset: str | None = None
    target_dir: Path
    name: str = Field(min_length=1)
    wait: bool = True
    timeout: float | None = Field(default=None, gt=0)

    @field_validator("target_dir")
    @classmethod
    def absolute_path(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("render target_dir must be absolute")
        return value


class EditPlan(StrictModel):
    version: Literal[1]
    project: ProjectSpec
    timeline: TimelineSpec
    media: list[MediaSpec] = Field(default_factory=list)
    edits: list[EditSpec] = Field(default_factory=list)
    captions: CaptionSpec = Field(default_factory=CaptionSpec)
    render: RenderSpec | None = None

    @model_validator(mode="after")
    def references_are_valid(self) -> "EditPlan":
        ids = [item.id for item in self.media]
        if len(ids) != len(set(ids)):
            raise ValueError("media ids must be unique")
        missing = sorted({edit.media for edit in self.edits} - set(ids))
        if missing:
            raise ValueError(f"edits reference unknown media ids: {', '.join(missing)}")
        return self


def load_plan(path: Path) -> EditPlan:
    if not path.is_absolute():
        path = path.resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return EditPlan.model_validate(payload)
    except FileNotFoundError as exc:
        raise ValidationFailure(f"Plan file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationFailure("Plan is not valid JSON", details={"line": exc.lineno, "column": exc.colno}) from exc
    except ValidationError as exc:
        raise ValidationFailure("Plan validation failed", details=exc.errors(include_url=False)) from exc


def timecode_to_frames(value: str, fps: float) -> int:
    parts = value.replace(";", ":").split(":")
    if len(parts) != 4 or any(not part.isdigit() for part in parts):
        raise ValidationFailure(f"Invalid SMPTE timecode: {value}")
    hours, minutes, seconds, frames = (int(part) for part in parts)
    nominal_fps = round(fps)
    if minutes >= 60 or seconds >= 60 or frames >= nominal_fps:
        raise ValidationFailure(f"Timecode is out of range for {fps} fps: {value}")
    return round(((hours * 60 + minutes) * 60 + seconds) * fps) + frames


def position_to_frames(position: TimePosition | None, fps: float) -> int | None:
    if position is None:
        return None
    if position.frames is not None:
        return position.frames
    if position.seconds is not None:
        return round(position.seconds * fps)
    return timecode_to_frames(position.timecode or "", fps)


def validate_plan(plan: EditPlan, *, check_files: bool = True) -> dict[str, Any]:
    problems: list[dict[str, Any]] = []
    if check_files:
        for media in plan.media:
            if not media.path.is_file():
                problems.append({"code": "media_not_found", "media": media.id, "path": str(media.path)})
    fps = plan.project.settings.frame_rate
    for index, edit in enumerate(plan.edits):
        source_in = position_to_frames(edit.source_in, fps)
        source_out = position_to_frames(edit.source_out, fps)
        if source_in is not None and source_out is not None and source_out <= source_in:
            problems.append({"code": "invalid_source_range", "edit": index, "source_in": source_in, "source_out": source_out})
    if problems:
        raise ValidationFailure("Plan preflight failed", details=problems)
    return {
        "valid": True,
        "version": plan.version,
        "media_count": len(plan.media),
        "edit_count": len(plan.edits),
        "will_render": plan.render is not None,
    }


class PlanExecutor:
    def __init__(self, service: ResolveService) -> None:
        self.service = service

    def apply(self, plan: EditPlan) -> dict[str, Any]:
        validate_plan(plan)
        completed: list[dict[str, Any]] = []
        try:
            projects = self.service.project_list()
            if plan.project.create:
                if plan.project.name in projects:
                    raise Conflict(f"Project already exists: {plan.project.name}")
                result = self.service.project_create(plan.project.name, plan.project.settings.model_dump())
                completed.append({"step": "project.create", "result": result})
            else:
                result = self.service.project_open(plan.project.name)
                completed.append({"step": "project.open", "result": result})

            timeline = self.service.timeline_create(plan.timeline.name, replace=plan.timeline.replace)
            completed.append({"step": "timeline.create", "result": timeline})
            timeline_start = int(self.service.current_timeline().GetStartFrame())

            imported = self.service.media_import([item.path for item in plan.media])
            completed.append({"step": "media.import", "count": len(imported)})
            imported_by_path = {str(Path(item.get("file_path", ""))): item for item in imported}

            fps = plan.project.settings.frame_rate
            media_identity: dict[str, tuple[str, float]] = {}
            for spec in plan.media:
                match = imported_by_path.get(str(spec.path))
                if not match:
                    match = next((item for item in imported if item["name"] == spec.path.name), None)
                if not match:
                    raise ResolveCLIError(f"Unable to identify imported media: {spec.path}")
                source_fps = float(match.get("properties", {}).get("FPS") or fps)
                media_identity[spec.id] = (match["id"], source_fps)

            for index, edit in enumerate(plan.edits):
                media_id, source_fps = media_identity[edit.media]
                relative_record_frame = position_to_frames(edit.record_at, fps)
                added = self.service.clip_append(
                    media_id,
                    source_in=position_to_frames(edit.source_in, source_fps),
                    source_out=position_to_frames(edit.source_out, source_fps),
                    track=edit.track,
                    record_at=(timeline_start + relative_record_frame) if relative_record_frame is not None else None,
                    media_type=edit.media_type,
                    properties=edit.properties,
                )
                completed.append({"step": "clip.append", "index": index, "count": len(added)})

            if plan.captions.auto:
                result = self.service.caption_auto(plan.captions.settings)
                completed.append({"step": "caption.auto", "result": result})

            if plan.render:
                result = self.service.render_start(
                    preset=plan.render.preset,
                    target_dir=plan.render.target_dir,
                    name=plan.render.name,
                    wait=plan.render.wait,
                    timeout=plan.render.timeout,
                )
                completed.append({"step": "render.start", "result": result})

            saved = self.service.project_save()
            completed.append({"step": "project.save", "result": saved})
            return {"applied": True, "completed_steps": completed}
        except ResolveCLIError as exc:
            raise ResolveCLIError(
                exc.message,
                code="partial_failure" if completed else exc.code,
                exit_code=ExitCode.PARTIAL_FAILURE if completed else exc.exit_code,
                details={"cause": exc.details, "completed_steps": completed},
            ) from exc
