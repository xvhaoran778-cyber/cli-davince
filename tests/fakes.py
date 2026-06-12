from __future__ import annotations

from pathlib import Path
from typing import Any


class FakeMediaItem:
    _counter = 0

    def __init__(self, path: str, fps: float = 50.0) -> None:
        FakeMediaItem._counter += 1
        self.path = path
        self.uid = f"media-{FakeMediaItem._counter}"
        self.fps = fps

    def GetUniqueId(self): return self.uid
    def GetMediaId(self): return f"mid-{self.uid}"
    def GetName(self): return Path(self.path).name
    def GetClipProperty(self, key=None):
        props = {"File Path": self.path, "File Name": Path(self.path).name, "FPS": self.fps}
        return props.get(key, "") if key else props


class FakeTimelineItem:
    _counter = 0

    def __init__(self, media, info):
        FakeTimelineItem._counter += 1
        self.media = media
        self.info = info
        self.uid = f"item-{FakeTimelineItem._counter}"
        self.properties = {}

    def GetUniqueId(self): return self.uid
    def GetName(self): return self.media.GetName()
    def GetStart(self, *args): return self.info.get("recordFrame", 0)
    def GetEnd(self, *args): return self.GetStart() + self.GetDuration()
    def GetDuration(self, *args): return self.info.get("endFrame", 99) - self.info.get("startFrame", 0) + 1
    def GetSourceStartFrame(self): return self.info.get("startFrame", 0)
    def GetSourceEndFrame(self): return self.info.get("endFrame", 99)
    def GetProperty(self, key=None): return self.properties.get(key) if key else self.properties
    def SetProperty(self, key, value): self.properties[key] = value; return True


class FakeFolder:
    def __init__(self): self.items = []
    def GetClipList(self): return self.items
    def GetSubFolderList(self): return []


class FakeTimeline:
    _counter = 0

    def __init__(self, name):
        FakeTimeline._counter += 1
        self.name = name
        self.uid = f"timeline-{FakeTimeline._counter}"
        self.tracks = {"video": [[]], "audio": [[]], "subtitle": []}

    def GetName(self): return self.name
    def GetUniqueId(self): return self.uid
    def GetStartFrame(self): return 90000
    def GetEndFrame(self): return max([item.GetEnd() for track in self.tracks.values() for items in track for item in items] or [0])
    def GetTrackCount(self, kind): return len(self.tracks[kind])
    def GetItemListInTrack(self, kind, index): return self.tracks[kind][index - 1]
    def GetTrackName(self, kind, index): return f"{kind.title()} {index}"
    def GetSetting(self, key): return "25"
    def DeleteClips(self, items, ripple=False):
        for tracks in self.tracks.values():
            for track in tracks:
                for item in items:
                    if item in track: track.remove(item)
        return True
    def CreateSubtitlesFromAudio(self, settings): return True


class FakeMediaPool:
    def __init__(self, project): self.project = project; self.root = FakeFolder(); self.last_append = None
    def GetRootFolder(self): return self.root
    def ImportMedia(self, paths):
        result = [FakeMediaItem(path) for path in paths]
        self.root.items.extend(result)
        return result
    def CreateEmptyTimeline(self, name):
        timeline = FakeTimeline(name); self.project.timelines.append(timeline); self.project.current = timeline; return timeline
    def DeleteTimelines(self, timelines):
        self.project.timelines = [x for x in self.project.timelines if x not in timelines]; return True
    def AppendToTimeline(self, infos):
        self.last_append = infos
        result = []
        for info in infos:
            item = FakeTimelineItem(info["mediaPoolItem"], info)
            kind = "audio" if info.get("mediaType") == 2 else "video"
            while len(self.project.current.tracks[kind]) < info.get("trackIndex", 1): self.project.current.tracks[kind].append([])
            self.project.current.tracks[kind][info.get("trackIndex", 1) - 1].append(item)
            result.append(item)
        return result


class FakeProject:
    _counter = 0

    def __init__(self, name):
        FakeProject._counter += 1
        self.name = name; self.uid = f"project-{FakeProject._counter}"; self.timelines = []; self.current = None
        self.pool = FakeMediaPool(self); self.settings = {}; self.jobs = {}; self.loaded_preset = None
    def GetName(self): return self.name
    def GetUniqueId(self): return self.uid
    def GetMediaPool(self): return self.pool
    def GetTimelineCount(self): return len(self.timelines)
    def GetTimelineByIndex(self, index): return self.timelines[index - 1]
    def GetCurrentTimeline(self): return self.current
    def SetCurrentTimeline(self, timeline): self.current = timeline; return True
    def SetSetting(self, key, value): self.settings[key] = value; return True
    def IsRenderingInProgress(self): return False
    def GetRenderPresetList(self): return ["YouTube 1080p"]
    def GetRenderFormats(self): return {"mp4": "mp4"}
    def GetRenderCodecs(self, fmt): return {"H.264": "H264"}
    def LoadRenderPreset(self, preset): self.loaded_preset = preset; return preset == "YouTube 1080p"
    def SetRenderSettings(self, settings): self.render_settings = settings; return True
    def AddRenderJob(self): self.jobs["job-1"] = {"JobStatus": "Complete"}; return "job-1"
    def StartRendering(self, jobs, interactive=False): return True
    def GetRenderJobStatus(self, job): return self.jobs.get(job)
    def GetRenderJobList(self): return list(self.jobs.values())


class FakeManager:
    def __init__(self): self.projects = {}; self.current = None
    def GetProjectListInCurrentFolder(self): return list(self.projects)
    def CreateProject(self, name):
        if name in self.projects: return None
        project = FakeProject(name); self.projects[name] = project; self.current = project; return project
    def LoadProject(self, name): self.current = self.projects.get(name); return self.current
    def GetCurrentProject(self): return self.current
    def SaveProject(self): return self.current is not None


class FakeResolve:
    def __init__(self): self.manager = FakeManager()
    def GetProjectManager(self): return self.manager
    def GetProductName(self): return "DaVinci Resolve Studio"
    def GetVersionString(self): return "20.2.0.00013"
    def GetCurrentPage(self): return "edit"


def fake_client(resolve=None):
    from cli_anything.resolve.resolve_client import ResolveClient
    resolve = resolve or FakeResolve()
    return ResolveClient(factory=lambda: resolve), resolve
