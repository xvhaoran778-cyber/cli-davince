---
name: cli-anything-resolve
description: Control DaVinci Resolve projects, media, timelines, clips, captions, and renders through an agent-friendly CLI.
---

# DaVinci Resolve CLI

Use `cli-anything-resolve --json` for machine-readable results. Resolve must already be running with local external scripting enabled.

Prefer declarative plans for multi-step edits:

```bash
cli-anything-resolve --json plan validate /absolute/edit-plan.json
cli-anything-resolve --json plan apply /absolute/edit-plan.json
```

Run `cli-anything-resolve doctor` before backend work. Use absolute media and render paths. Never pass `--replace` or destructive `--yes` flags without explicit user intent.

