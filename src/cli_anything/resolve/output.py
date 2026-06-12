from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import click


def _default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return str(value)


def emit(data: Any, *, json_output: bool, message: str | None = None) -> None:
    if json_output:
        click.echo(json.dumps({"ok": True, "data": data}, ensure_ascii=False, default=_default))
        return
    if message:
        click.echo(message)
    elif isinstance(data, (dict, list)):
        click.echo(json.dumps(data, ensure_ascii=False, indent=2, default=_default))
    else:
        click.echo(str(data))


def emit_error(error: Exception, *, json_output: bool) -> None:
    from .errors import ResolveCLIError

    if isinstance(error, ResolveCLIError):
        payload = {"code": error.code, "message": error.message, "details": error.details}
    else:
        payload = {"code": "internal_error", "message": str(error), "details": None}
    if json_output:
        click.echo(json.dumps({"ok": False, "error": payload}, ensure_ascii=False, default=_default), err=True)
    else:
        click.echo(f"Error [{payload['code']}]: {payload['message']}", err=True)

