from __future__ import annotations

from enum import IntEnum
from typing import Any


class ExitCode(IntEnum):
    OK = 0
    USAGE = 2
    VALIDATION = 3
    NOT_FOUND = 4
    CONFLICT = 5
    BACKEND_UNAVAILABLE = 10
    BACKEND_FAILURE = 11
    PARTIAL_FAILURE = 12


class ResolveCLIError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "backend_failure",
        exit_code: ExitCode = ExitCode.BACKEND_FAILURE,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.exit_code = exit_code
        self.details = details


class BackendUnavailable(ResolveCLIError):
    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(
            message,
            code="backend_unavailable",
            exit_code=ExitCode.BACKEND_UNAVAILABLE,
            details=details,
        )


class ValidationFailure(ResolveCLIError):
    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(
            message,
            code="validation_error",
            exit_code=ExitCode.VALIDATION,
            details=details,
        )


class NotFound(ResolveCLIError):
    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message, code="not_found", exit_code=ExitCode.NOT_FOUND, details=details)


class Conflict(ResolveCLIError):
    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message, code="conflict", exit_code=ExitCode.CONFLICT, details=details)

