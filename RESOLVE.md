# Resolve Harness Architecture

The package is split into four layers:

- `resolve_client` locates and loads Blackmagic's SDK and connects to an already-running Resolve process.
- `services` provides checked operations over projects, Media Pool items, timelines, clips, captions, and rendering.
- `plan` validates versioned JSON edit plans, converts time units to frames, performs preflight, and executes steps sequentially.
- `cli` exposes Click commands with consistent human and JSON output.

The harness deliberately avoids GUI automation. It only exposes behavior available through the installed Resolve Scripting API. A failed plan reports completed steps and leaves them intact so it never destroys unrelated user work while attempting an implicit rollback.

Exit codes are stable: `0` success, `2` CLI usage, `3` validation, `4` missing resource, `5` conflict, `10` backend unavailable, `11` backend failure, and `12` partial plan failure.

