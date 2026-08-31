"""
Transcript Logger - PR-Review Agent
Collects agent interactions and writes them as JSONL.
Used for: {id}_transcript.jsonl (full flow) and judge_transcript.jsonl (judge only)
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class TranscriptLogger:
    """
    Accumulates structured interaction records and writes them as JSONL.

    Each record has the shape:
    {
        "timestamp": ISO-8601,
        "step": str,          # e.g. "scanner", "merger", "debate", "judge"
        "agent": str,         # agent name / role
        "action": str,        # e.g. "call", "response"
        "input_summary": str, # truncated prompt / input
        "output_summary": str,# truncated response
        "duration_ms": int,   # wall-clock milliseconds
        "metadata": dict      # anything extra (round number, etc.)
    }
    """

    def __init__(self) -> None:
        self._records: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log(
        self,
        *,
        step: str,
        agent: str,
        action: str,
        input_text: str = "",
        output_text: str = "",
        duration_ms: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Append one interaction record."""
        self._records.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "step": step,
            "agent": agent,
            "action": action,
            "input_summary": _truncate(input_text, 2000),
            "output_summary": _truncate(output_text, 2000),
            "duration_ms": duration_ms,
            "metadata": metadata or {},
        })

    @property
    def records(self) -> List[Dict[str, Any]]:
        return list(self._records)

    @property
    def empty(self) -> bool:
        return len(self._records) == 0

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_jsonl(self, filepath: str) -> None:
        """Write all records to a JSONL file (one JSON object per line)."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for rec in self._records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # Convenience: save the "input" dict that was sent to the judge
    # ------------------------------------------------------------------

    @staticmethod
    def save_json(data: Any, filepath: str) -> None:
        """Write a JSON-serialisable object to *filepath*."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"... [截断，共 {len(text)} 字符]"