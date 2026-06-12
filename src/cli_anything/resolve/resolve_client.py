from __future__ import annotations

import importlib.util
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .errors import BackendUnavailable


@dataclass(frozen=True)
class SDKPaths:
    api_dir: Path
    module_file: Path
    library_file: Path


def default_sdk_paths(system: str | None = None, env: dict[str, str] | None = None) -> SDKPaths:
    system = system or platform.system()
    env = env or os.environ
    api_override = env.get("RESOLVE_SCRIPT_API")
    lib_override = env.get("RESOLVE_SCRIPT_LIB")

    if system == "Darwin":
        api_dir = Path(api_override or "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting")
        module_file = api_dir / "Modules" / "DaVinciResolveScript.py"
        library_file = Path(lib_override or "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so")
    elif system == "Windows":
        base = Path(env.get("PROGRAMDATA", r"C:\ProgramData")) / "Blackmagic Design/DaVinci Resolve/Support/Developer/Scripting"
        api_dir = Path(api_override) if api_override else base
        module_file = api_dir / "Modules" / "DaVinciResolveScript.py"
        library_file = Path(lib_override or r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll")
    elif system == "Linux":
        api_dir = Path(api_override or "/opt/resolve/Developer/Scripting")
        module_file = api_dir / "Modules" / "DaVinciResolveScript.py"
        library_file = Path(lib_override or "/opt/resolve/libs/Fusion/fusionscript.so")
    else:
        raise BackendUnavailable(f"Unsupported operating system: {system}")
    return SDKPaths(api_dir=api_dir, module_file=module_file, library_file=library_file)


class ResolveClient:
    def __init__(self, factory: Callable[[], Any] | None = None) -> None:
        self._factory = factory
        self._resolve: Any = None

    @property
    def paths(self) -> SDKPaths:
        return default_sdk_paths()

    def sdk_status(self) -> dict[str, Any]:
        paths = self.paths
        return {
            "api_dir": str(paths.api_dir),
            "module_file": str(paths.module_file),
            "library_file": str(paths.library_file),
            "module_found": paths.module_file.is_file(),
            "library_found": paths.library_file.is_file(),
            "python_supported": (3, 10) <= sys.version_info[:2] < (3, 14),
        }

    def _load_module(self) -> Any:
        paths = self.paths
        if not paths.module_file.is_file():
            raise BackendUnavailable("DaVinci Resolve scripting module was not found", details=self.sdk_status())
        if not paths.library_file.is_file():
            raise BackendUnavailable(
                "DaVinci Resolve scripting library was not found; set RESOLVE_SCRIPT_LIB for non-default installations",
                details=self.sdk_status(),
            )
        os.environ.setdefault("RESOLVE_SCRIPT_API", str(paths.api_dir))
        os.environ.setdefault("RESOLVE_SCRIPT_LIB", str(paths.library_file))
        spec = importlib.util.spec_from_file_location("DaVinciResolveScript", paths.module_file)
        if not spec or not spec.loader:
            raise BackendUnavailable("Unable to load DaVinciResolveScript module specification")
        module = importlib.util.module_from_spec(spec)
        sys.modules["DaVinciResolveScript"] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            raise BackendUnavailable(
                "Unable to load Resolve native scripting library; use a Resolve-compatible Python 3.10-3.13 runtime",
                details=str(exc),
            ) from exc
        # Blackmagic's shim replaces its own sys.modules entry with the native
        # fusionscript extension while executing.
        return sys.modules.get("DaVinciResolveScript", module)

    def connect(self) -> Any:
        if self._resolve is not None:
            return self._resolve
        try:
            self._resolve = self._factory() if self._factory else self._load_module().scriptapp("Resolve")
        except BackendUnavailable:
            raise
        except Exception as exc:
            raise BackendUnavailable("Failed to connect to DaVinci Resolve", details=str(exc)) from exc
        if self._resolve is None:
            raise BackendUnavailable(
                "DaVinci Resolve is not running or external scripting is disabled",
                details="Start Resolve and enable local external scripting in Preferences > System > General.",
            )
        return self._resolve

    def doctor(self) -> dict[str, Any]:
        result = self.sdk_status()
        try:
            resolve = self.connect()
            result.update(
                connected=True,
                product=resolve.GetProductName(),
                version=resolve.GetVersionString(),
                current_page=resolve.GetCurrentPage(),
            )
        except BackendUnavailable as exc:
            result.update(connected=False, connection_error=exc.message, hint=exc.details)
        result["healthy"] = all(
            [result["module_found"], result["library_found"], result["python_supported"], result["connected"]]
        )
        return result
