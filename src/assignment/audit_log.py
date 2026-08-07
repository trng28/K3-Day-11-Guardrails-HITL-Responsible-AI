"""
Assignment 11 — Audit Log starter (TODO).

Records every interaction for forensics. Never blocks by itself —
other layers catch attacks; this layer makes them reviewable.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class AuditLogPlugin:
    """Framework-neutral audit logger with request correlation."""

    def __init__(self):
        self.name = "audit_log"
        self.logs: list[dict] = []
        self._open: dict[str, float] = {}
        self._latest_by_user: dict[str, str] = {}

    def record_input(self, *, user_id: str, text: str, request_id: str | None = None):
        """Record an input event and return its stable correlation ID."""
        correlation_id = request_id or f"REQ-{uuid4().hex.upper()}"
        if correlation_id in self._open:
            raise ValueError(f"request_id is already open: {correlation_id}")

        self._open[correlation_id] = time.perf_counter()
        self._latest_by_user[user_id] = correlation_id
        self.logs.append({
            "request_id": correlation_id,
            "event": "input",
            "timestamp": utc_now_iso(),
            "user_id": user_id,
            "text": text,
            "layer": "input",
            "decision": "received",
        })
        return correlation_id

    def record_output(
        self,
        *,
        user_id: str,
        text: str,
        blocked: bool = False,
        layer: str | None = None,
        request_id: str | None = None,
        reviewer_id: str | None = None,
        reviewer_decision: str | None = None,
        action: str | None = None,
        action_decision: str | None = None,
        metadata: dict | None = None,
    ):
        """Record output, policy/HITL decisions and end-to-end latency."""
        correlation_id = request_id or self._latest_by_user.get(user_id)
        if correlation_id is None:
            correlation_id = f"REQ-{uuid4().hex.upper()}"

        started_at = self._open.pop(correlation_id, None)
        latency_ms = (
            round((time.perf_counter() - started_at) * 1000, 3)
            if started_at is not None
            else None
        )
        if self._latest_by_user.get(user_id) == correlation_id:
            self._latest_by_user.pop(user_id, None)

        record = {
            "request_id": correlation_id,
            "event": "output",
            "timestamp": utc_now_iso(),
            "user_id": user_id,
            "text": text,
            "blocked": blocked,
            "layer": layer or "output",
            "decision": "blocked" if blocked else "allowed",
            "latency_ms": latency_ms,
            "reviewer_id": reviewer_id,
            "reviewer_decision": reviewer_decision,
            "action": action,
            "action_decision": action_decision,
        }
        if metadata:
            record["metadata"] = dict(metadata)
        self.logs.append(record)
        return record

    def find_by_request_id(self, request_id: str) -> list[dict]:
        """Return every audit event belonging to one request."""
        return [row for row in self.logs if row.get("request_id") == request_id]

    def export_json(self, filepath: str = "outputs/audit_log.json"):
        """Write logs to disk (JSON array)."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.logs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
