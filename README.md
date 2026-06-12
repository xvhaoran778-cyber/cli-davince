# cli-anything-resolve

Agent-friendly command-line control for DaVinci Resolve using Blackmagic Design's official scripting API.

## Requirements

- Python 3.10 through 3.13
- DaVinci Resolve with external scripting enabled for local applications
- Resolve must already be running before commands that connect to it

DaVinci Resolve Studio 20.2 on macOS is the reference environment. Windows and Linux SDK paths are supported but are not part of the initial real-backend test matrix.

## Install

```bash
python3.13 -m venv .venv
.venv/bin/pip install '.[dev]'
cli-anything-resolve doctor
```

For a non-default Resolve installation, set the SDK locations explicitly:

```bash
export RESOLVE_SCRIPT_API="/path/to/Developer/Scripting"
export RESOLVE_SCRIPT_LIB="/path/to/fusionscript.so"
```

## Examples

```bash
cli-anything-resolve --json status
cli-anything-resolve project create Demo --frame-rate 25
cli-anything-resolve media import /absolute/path/intro.mp4
cli-anything-resolve timeline create Main
cli-anything-resolve clip append intro.mp4 --source-in 50 --source-out 200
cli-anything-resolve render start --preset "YouTube - 1080p" \
  --target-dir /absolute/output --name demo --wait
```

Every command supports structured output through the root `--json` option. Destructive timeline and clip deletion require `--yes`. Existing timelines are never replaced unless `timeline create --replace` or a plan with `"replace": true` is used.

## Edit Plans

Validate and execute a repeatable editing workflow:

```bash
cli-anything-resolve --json plan validate edit-plan.json
cli-anything-resolve --json plan apply edit-plan.json
```

Time positions accept exactly one of `frames`, `seconds`, or SMPTE `timecode`. Source positions use each media item's frame rate, while `record_at` uses the timeline frame rate and is relative to the timeline start. `source_out` is exclusive in the public plan format and is converted to Resolve's inclusive source end frame internally.

See [RESOLVE.md](RESOLVE.md) for architecture and backend behavior.
An editable starting point is available at [examples/edit-plan.example.json](examples/edit-plan.example.json).

## Privacy and agent safety

The CLI talks directly to the locally running Resolve scripting API and does not upload projects or media. Commands such as `project list`, `media list`, and `timeline inspect` can return project names and absolute media paths, so treat their JSON output as private when using a hosted agent. Keep Resolve external scripting set to local access unless remote control is explicitly required.

Local `edit-plan.json`, `.env` files, source media, Resolve project archives, and common render-output directories are ignored by Git. Commit only sanitized examples with placeholder paths.
