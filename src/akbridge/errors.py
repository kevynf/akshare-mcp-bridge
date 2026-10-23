"""Structured, LLM-friendly error responses for AKBridge MCP tools.

The MCP wire protocol reports tool failures as ``isError=true`` with free-form
text content.  The official SDK stringifies raised exceptions into the tool's
``TextContent``.  :class:`AKBridgeError` therefore serialises its canonical
JSON payload as ``str(self)`` so an LLM client can parse ``content[0].text``
and read a stable ``error.code`` plus recovery hints without inspecting
natural-language text.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Stable, machine-readable error codes surfaced to MCP clients."""

    UNKNOWN_API = "UNKNOWN_API"
    TOOL_NOT_AVAILABLE = "TOOL_NOT_AVAILABLE"
    SCHEMA_VIOLATION = "SCHEMA_VIOLATION"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    RATE_LIMITED = "RATE_LIMITED"
    SIDE_EFFECT_DENIED = "SIDE_EFFECT_DENIED"
    UNKNOWN_RESOURCE = "UNKNOWN_RESOURCE"
    UNKNOWN_PROMPT = "UNKNOWN_PROMPT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AKBridgeError(Exception):
    """An exception whose ``str()`` is the canonical JSON error payload.

    Attributes:
        code: One of :class:`ErrorCode`.
        message: Short human-readable description.
        suggestions: Optional list of alternative API names or next steps.
        retry_hint: Natural-language recovery strategy for the LLM.
        details: Optional extra structured context (e.g. ``{"parameter": "..."}``).
    """

    def __init__(
        self,
        code: ErrorCode | str,
        message: str,
        *,
        suggestions: list[str] | None = None,
        retry_hint: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = ErrorCode(code)
        self.message = message
        self.suggestions = list(suggestions or [])
        self.retry_hint = retry_hint
        self.details = dict(details or {})

    def to_payload(self) -> dict[str, Any]:
        """Return the canonical JSON document sent to MCP clients."""
        body: dict[str, Any] = {"code": str(self.code), "message": self.message}
        if self.suggestions:
            body["suggestions"] = self.suggestions
        if self.retry_hint:
            body["retry_hint"] = self.retry_hint
        if self.details:
            body["details"] = self.details
        return {"error": body}

    def __str__(self) -> str:
        # The MCP low-level SDK stringifies raised exceptions into the tool's
        # TextContent when isError=true, so we emit the JSON payload directly.
        return json.dumps(self.to_payload(), ensure_ascii=False, default=str)


def classify_exception(exc: BaseException) -> ErrorCode:
    """Map an arbitrary provider or validation exception to a stable code."""
    from .reliability import CircuitOpenError  # local to avoid import cycle

    if isinstance(exc, AKBridgeError):
        return exc.code
    if isinstance(exc, CircuitOpenError):
        return ErrorCode.CIRCUIT_OPEN
    exception_name = type(exc).__name__.casefold()
    module_name = type(exc).__module__.casefold()
    if "timeout" in exception_name:
        return ErrorCode.UPSTREAM_TIMEOUT
    response = getattr(exc, "response", None)
    status_code = (
        getattr(exc, "status_code", None)
        or getattr(exc, "code", None)
        or getattr(response, "status_code", None)
        or getattr(response, "code", None)
    )
    if status_code == 429:
        return ErrorCode.RATE_LIMITED
    if status_code in {400, 422}:
        return ErrorCode.INVALID_ARGUMENT
    if isinstance(status_code, int) and status_code >= 400:
        return ErrorCode.UPSTREAM_ERROR
    if isinstance(exc, TimeoutError):
        return ErrorCode.UPSTREAM_TIMEOUT
    if isinstance(exc, (ConnectionError, OSError)) or (
        module_name.startswith(("httpx", "requests", "urllib3"))
        and any(token in exception_name for token in ("connect", "network", "transport", "request"))
    ):
        return ErrorCode.UPSTREAM_ERROR
    if isinstance(exc, KeyError):
        return ErrorCode.UNKNOWN_API
    if isinstance(exc, (TypeError, ValueError)):
        return ErrorCode.INVALID_ARGUMENT
    return ErrorCode.INTERNAL_ERROR


def wrap_exception(
    exc: BaseException,
    *,
    retry_hint: str | None = None,
    suggestions: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> AKBridgeError:
    """Coerce any exception into an :class:`AKBridgeError` with a stable code."""
    if isinstance(exc, AKBridgeError):
        if retry_hint and not exc.retry_hint:
            exc.retry_hint = retry_hint
        if suggestions and not exc.suggestions:
            exc.suggestions = list(suggestions)
        if details:
            exc.details.update(details)
        return exc
    from .reliability import redact_secrets  # local to keep dependencies one-way

    safe_message = redact_secrets(str(exc) or type(exc).__name__)
    return AKBridgeError(
        classify_exception(exc),
        str(safe_message),
        suggestions=suggestions,
        retry_hint=retry_hint,
        details=details,
    )
