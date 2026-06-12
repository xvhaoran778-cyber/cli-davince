from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Iterable

from .errors import Conflict, NotFound, ResolveCLIError, ValidationFailure
from .resolve_client import ResolveClient


def require(value: Any, message: str) -> Any:
    if value is None or value is False:
        raise ResolveCLIError(message)
    return value


def serialize_media(item: Any) -> dict[str, Any]:
    props = item.GetClipProperty() or {}
    return {
        "id": item.GetUniqueId(),
        "media_id": item.GetMediaId() if hasattr(item, "GetMediaId") else None,
        "name": item.GetName(),
        "file_path": props.get("File Path") or props.get("File Path ") or props.get("File Name"),
        "properties": props,
    }


def serialize_item(item: Any, track_type: str, track: int) -> dict[str, Any]:
    return {
        "id": item.GetUniqueId(),
        "name": item.GetName(),
        "track_type": track_type,
        "track": track,
        "start": item.GetStart(),
        "end": item.GetEnd(),
        "duration": item.GetDuration(),
        "source_start": item.GetSourceStartFrame(),
        "source_end": item.GetSourceEndFrame(),
        "properties": item.GetProperty() or {},
    }


class ResolveService:
    def __init__(self, client: ResolveClient) -> None:
        self.client = client

    @property
    def resolve(self) -> Any:
        return self.client.connect()

    @property
    def manager(self) -> Any:
        return require(self.resolve.GetProjectManager(), "Resolve project manager is unavailable")

    def current_project(self) -> Any:
        project = self.manager.GetCurrentProject()
        if not project:
            raise NotFound("No Resolve project is currently open")
        return project

    def current_timeline(self) -> Any:
        timeline = self.current_project().GetCurrentTimeline()
        if not timeline:
            raise NotFound("No timeline is currently selected")
        return timeline

    def status(self) -> dict[str, Any]:
        resolve = self.resolve
        project = self.manager.GetCurrentProject()
        timeline = project.GetCurrentTimeline() if project else None
        return {
            "product": resolve.GetProductName(),
            "version": resolve.GetVersionString(),
            "page": resolve.GetCurrentPage(),
            "project": project.GetName() if project else None,
            "timeline": timeline.GetName() if timeline else None,
            "rendering": bool(project and project.IsRenderingInProgress()),
        }

    def project_list(self) -> list[str]:
        return list(self.manager.GetProjectListInCurrentFolder() or [])

    def project_create(self, name: str, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        project = self.manager.CreateProject(name)
        if not project:
            raise Conflict(f"Project already exists or could not be created: {name}")
        mapping = {
            "frame_rate": "timelineFrameRate",
            "width": "timelineResolutionWidth",
            "height": "timelineResolutionHeight",
        }
        for key, value in (settings or {}).items():
            if key in mapping and not project.SetSetting(mapping[key], str(value)):
                raise ResolveCLIError(f"Unable to set project setting {key}={value}")
        self.manager.SaveProject()
        return {"name": project.GetName(), "created": True}

    def project_open(self, name: str) -> dict[str, Any]:
        project = self.manager.LoadProject(name)
        if not project:
            raise NotFound(f"Project not found: {name}")
        return {"name": project.GetName(), "opened": True}

    def project_info(self) -> dict[str, Any]:
        project = self.current_project()
        return {"name": project.GetName(), "id": project.GetUniqueId(), "timeline_count": project.GetTimelineCount()}

    def project_save(self) -> dict[str, Any]:
        require(self.manager.SaveProject(), "Unable to save current project")
        return {"saved": True, "name": self.current_project().GetName()}

    def _walk_folder(self, folder: Any) -> Iterable[Any]:
        yield from folder.GetClipList() or []
        for child in folder.GetSubFolderList() or []:
            yield from self._walk_folder(child)

    def media_list(self) -> list[dict[str, Any]]:
        root = self.current_project().GetMediaPool().GetRootFolder()
        return [serialize_media(item) for item in self._walk_folder(root)]

    def media_import(self, paths: list[Path]) -> list[dict[str, Any]]:
        bad = [str(path) for path in paths if not path.is_absolute() or not path.exists()]
        if bad:
            raise ValidationFailure("Media paths must be absolute and exist", details=bad)
        items = self.current_project().GetMediaPool().ImportMedia([str(path) for path in paths])
        if not items:
            raise ResolveCLIError("Resolve did not import any media")
        return [serialize_media(item) for item in items]

    def timeline_list(self) -> list[dict[str, Any]]:
        project = self.current_project()
        return [
            {"index": index, "id": timeline.GetUniqueId(), "name": timeline.GetName()}
            for index in range(1, int(project.GetTimelineCount()) + 1)
            if (timeline := project.GetTimelineByIndex(index))
        ]

    def find_timeline(self, identity: str | None = None) -> Any:
        if not identity:
            return self.current_timeline()
        for entry in self.timeline_list():
            if identity in {entry["id"], entry["name"], str(entry["index"])}:
                return self.current_project().GetTimelineByIndex(entry["index"])
        raise NotFound(f"Timeline not found: {identity}")

    def timeline_create(self, name: str, replace: bool = False) -> dict[str, Any]:
        project = self.current_project()
        existing = next((entry for entry in self.timeline_list() if entry["name"] == name), None)
        if existing and not replace:
            raise Conflict(f"Timeline already exists: {name}")
        if existing:
            old = project.GetTimelineByIndex(existing["index"])
            require(project.GetMediaPool().DeleteTimelines([old]), f"Unable to replace timeline: {name}")
        timeline = project.GetMediaPool().CreateEmptyTimeline(name)
        require(timeline, f"Unable to create timeline: {name}")
        require(project.SetCurrentTimeline(timeline), f"Unable to select timeline: {name}")
        return {"name": timeline.GetName(), "id": timeline.GetUniqueId(), "created": True, "replaced": bool(existing)}

    def timeline_delete(self, identity: str) -> dict[str, Any]:
        timeline = self.find_timeline(identity)
        name = timeline.GetName()
        require(self.current_project().GetMediaPool().DeleteTimelines([timeline]), f"Unable to delete timeline: {name}")
        return {"deleted": True, "name": name}

    def timeline_inspect(self, identity: str | None = None) -> dict[str, Any]:
        timeline = self.find_timeline(identity)
        tracks: dict[str, list[dict[str, Any]]] = {}
        for track_type in ("video", "audio", "subtitle"):
            tracks[track_type] = []
            for index in range(1, int(timeline.GetTrackCount(track_type)) + 1):
                items = [serialize_item(item, track_type, index) for item in timeline.GetItemListInTrack(track_type, index) or []]
                tracks[track_type].append({"index": index, "name": timeline.GetTrackName(track_type, index), "items": items})
        return {
            "id": timeline.GetUniqueId(),
            "name": timeline.GetName(),
            "start_frame": timeline.GetStartFrame(),
            "end_frame": timeline.GetEndFrame(),
            "frame_rate": float(timeline.GetSetting("timelineFrameRate")),
            "tracks": tracks,
        }

    def _find_media(self, identity: str) -> Any:
        root = self.current_project().GetMediaPool().GetRootFolder()
        for item in self._walk_folder(root):
            props = item.GetClipProperty() or {}
            candidates = {item.GetUniqueId(), item.GetName(), item.GetMediaId(), props.get("File Path"), props.get("File Name")}
            if identity in candidates:
                return item
        raise NotFound(f"Media not found: {identity}")

    def clip_append(
        self,
        media: str,
        *,
        source_in: int | None = None,
        source_out: int | None = None,
        track: int = 1,
        record_at: int | None = None,
        media_type: str = "all",
        properties: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        item = self._find_media(media)
        info: dict[str, Any] = {"mediaPoolItem": item, "trackIndex": track}
        if source_in is not None:
            info["startFrame"] = source_in
        if source_out is not None:
            if source_in is not None and source_out <= source_in:
                raise ValidationFailure("source_out must be greater than source_in")
            info["endFrame"] = source_out - 1
        if record_at is not None:
            info["recordFrame"] = record_at
        if media_type != "all":
            info["mediaType"] = {"video": 1, "audio": 2}[media_type]
        added = self.current_project().GetMediaPool().AppendToTimeline([info])
        if not added:
            raise ResolveCLIError(f"Unable to append media to timeline: {media}")
        for timeline_item in added:
            for key, value in (properties or {}).items():
                require(timeline_item.SetProperty(key, value), f"Unable to set clip property {key}={value}")
        return [serialize_item(x, "video" if media_type != "audio" else "audio", track) for x in added]

    def _find_timeline_item(self, identity: str) -> tuple[Any, str, int]:
        timeline = self.current_timeline()
        for track_type in ("video", "audio", "subtitle"):
            for index in range(1, int(timeline.GetTrackCount(track_type)) + 1):
                for item in timeline.GetItemListInTrack(track_type, index) or []:
                    if identity in {item.GetUniqueId(), item.GetName()}:
                        return item, track_type, index
        raise NotFound(f"Timeline clip not found: {identity}")

    def clip_delete(self, identity: str, ripple: bool = False) -> dict[str, Any]:
        item, _, _ = self._find_timeline_item(identity)
        require(self.current_timeline().DeleteClips([item], ripple), f"Unable to delete clip: {identity}")
        return {"deleted": True, "id": identity, "ripple": ripple}

    def clip_set_property(self, identity: str, key: str, value: Any) -> dict[str, Any]:
        item, _, _ = self._find_timeline_item(identity)
        require(item.SetProperty(key, value), f"Unable to set clip property {key}")
        return {"id": identity, "property": key, "value": value}

    def caption_auto(self, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        timeline = self.current_timeline()
        if not hasattr(timeline, "CreateSubtitlesFromAudio"):
            raise ResolveCLIError("This Resolve version does not support automatic captions")
        require(timeline.CreateSubtitlesFromAudio(settings or {}), "Unable to create subtitles from timeline audio")
        return {"started": True, "timeline": timeline.GetName()}

    def render_presets(self) -> list[Any]:
        return list(self.current_project().GetRenderPresetList() or [])

    def render_formats(self) -> dict[str, Any]:
        project = self.current_project()
        formats = project.GetRenderFormats() or {}
        return {name: {"extension": extension, "codecs": project.GetRenderCodecs(name) or {}} for name, extension in formats.items()}

    def render_start(
        self,
        *,
        preset: str | None,
        target_dir: Path,
        name: str,
        wait: bool = False,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if not target_dir.is_absolute():
            raise ValidationFailure("Render target directory must be absolute")
        target_dir.mkdir(parents=True, exist_ok=True)
        project = self.current_project()
        if preset and not project.LoadRenderPreset(preset):
            raise NotFound(f"Render preset not found: {preset}")
        require(project.SetRenderSettings({"SelectAllFrames": True, "TargetDir": str(target_dir), "CustomName": name}), "Unable to set render settings")
        job_id = project.AddRenderJob()
        require(job_id, "Unable to add render job")
        require(project.StartRendering([job_id], False), "Unable to start render job")
        result = {"job_id": job_id, "started": True, "target_dir": str(target_dir), "name": name}
        if wait:
            result["status"] = self.render_wait(job_id, timeout=timeout)
        return result

    def render_status(self, job_id: str | None = None) -> Any:
        project = self.current_project()
        if job_id:
            status = project.GetRenderJobStatus(job_id)
            if not status:
                raise NotFound(f"Render job not found: {job_id}")
            return status
        return {"rendering": bool(project.IsRenderingInProgress()), "jobs": project.GetRenderJobList() or []}

    def render_wait(self, job_id: str, *, timeout: float | None = None, interval: float = 0.5) -> dict[str, Any]:
        started = time.monotonic()
        terminal_statuses = {
            "complete", "completed", "failed", "cancelled", "canceled",
            "完成", "失败", "取消", "已取消",
        }
        while True:
            status = self.render_status(job_id)
            job_status = str(status.get("JobStatus", "")).strip().lower()
            completion = status.get("CompletionPercentage")
            if job_status in terminal_statuses or (isinstance(completion, (int, float)) and completion >= 100):
                return status
            if timeout is not None and time.monotonic() - started > timeout:
                raise ResolveCLIError(f"Timed out waiting for render job: {job_id}", code="render_timeout")
            time.sleep(interval)
