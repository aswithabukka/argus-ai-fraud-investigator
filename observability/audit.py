"""Per-case audit trail — the observability / production pillar.

Every agent invocation, tool call, decision, and critic verdict is appended in
order, then saved as JSON per case. In a real fraud op this is the immutable
record a regulator or a disputing customer could later review.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import config


class AuditTrail:
    def __init__(self, txn_id: int) -> None:
        self.txn_id = txn_id
        self.steps: list[dict[str, Any]] = []

    def log(self, agent: str, action: str, detail: Any = None,
            tool_calls: list[dict] | None = None) -> None:
        self.steps.append({
            "seq": len(self.steps) + 1,
            "agent": agent,
            "action": action,
            "detail": detail,
            "tool_calls": tool_calls or [],
        })

    def save(self) -> Path:
        config.AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        path = config.AUDIT_DIR / f"case_{self.txn_id}.json"
        path.write_text(json.dumps(
            {"txn_id": self.txn_id, "steps": self.steps}, indent=2, default=str
        ))
        return path

    def render(self) -> str:
        """Human-readable trace for the demo cell."""
        lines = [f"=== AUDIT TRAIL — case {self.txn_id} ==="]
        for s in self.steps:
            lines.append(f"[{s['seq']:02d}] {s['agent']:<14} · {s['action']}")
            for tc in s["tool_calls"]:
                lines.append(f"        ↳ tool: {tc.get('name')}({_fmt_args(tc.get('args', {}))})")
            if s["detail"] is not None:
                lines.append(f"        {_fmt_detail(s['detail'])}")
        return "\n".join(lines)


def _fmt_args(args: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in args.items())


def _fmt_detail(detail: Any) -> str:
    text = detail if isinstance(detail, str) else json.dumps(detail, default=str)
    return text if len(text) <= 200 else text[:197] + "..."
