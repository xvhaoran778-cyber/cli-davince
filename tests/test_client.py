from cli_anything.resolve.resolve_client import default_sdk_paths


def test_platform_paths_and_overrides():
    paths = default_sdk_paths("Linux", {"RESOLVE_SCRIPT_API": "/sdk", "RESOLVE_SCRIPT_LIB": "/lib/fusion.so"})
    assert str(paths.module_file) == "/sdk/Modules/DaVinciResolveScript.py"
    assert str(paths.library_file) == "/lib/fusion.so"


def test_windows_default_path():
    paths = default_sdk_paths("Windows", {"PROGRAMDATA": r"D:\Data"})
    assert "Blackmagic Design" in str(paths.module_file)
    assert paths.library_file.suffix == ".dll"

