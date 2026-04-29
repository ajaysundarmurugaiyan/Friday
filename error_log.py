"""
error_log.py — Global error registry for the Friday assistant.

Every tool appends errors here via log_error().
The check_system_errors tool reads from here so the agent can
explain what went wrong and suggest fixes when the user asks.
"""

import time
from typing import Optional

# ---------------------------------------------------------------------------
# In-memory error store (persists for the lifetime of the agent process)
# ---------------------------------------------------------------------------

_errors: list[dict] = []

MAX_ERRORS = 100  # prevent unbounded growth over long sessions


def log_error(
    source: str,
    error: str,
    detail: Optional[str] = None,
    suggestion: Optional[str] = None,
) -> None:
    """
    Append an error entry to the global log.

    Args:
        source:     Which tool/component raised the error (e.g. 'send_email', 'get_weather').
        error:      Short human-readable error description.
        detail:     Full traceback or raw exception string (optional).
        suggestion: Actionable fix suggestion (optional).
    """
    entry = {
        "id":         len(_errors) + 1,
        "timestamp":  int(time.time() * 1000),
        "time_str":   time.strftime("%H:%M:%S"),
        "source":     source,
        "error":      error,
        "detail":     detail or "",
        "suggestion": suggestion or "",
    }
    _errors.append(entry)

    # Trim to keep the most recent MAX_ERRORS entries
    if len(_errors) > MAX_ERRORS:
        _errors.pop(0)


def get_all_errors() -> list[dict]:
    """Return a copy of all logged errors."""
    return list(_errors)


def get_recent_errors(n: int = 10) -> list[dict]:
    """Return the most recent n errors."""
    return list(_errors[-n:])


def clear_errors() -> None:
    """Clear the error log (called by the clear_error_log tool)."""
    _errors.clear()


def format_errors_for_agent(errors: list[dict]) -> str:
    """Format error list into a readable report for the agent to speak."""
    if not errors:
        return "No errors have been logged in this session."

    lines = [f"━━━ SYSTEM ERROR LOG ({len(errors)} error(s)) ━━━", ""]
    for e in errors:
        lines.append(f"[{e['id']}] {e['time_str']} — {e['source'].upper()}")
        lines.append(f"    Error      : {e['error']}")
        if e["detail"]:
            # Truncate very long tracebacks so the agent isn't overwhelmed
            detail_preview = e["detail"][:500] + ("..." if len(e["detail"]) > 500 else "")
            lines.append(f"    Detail     : {detail_preview}")
        if e["suggestion"]:
            lines.append(f"    Suggestion : {e['suggestion']}")
        lines.append("")

    return "\n".join(lines)
