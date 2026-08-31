"""
Flow Base Class - PR-Review Agent
Unified interface for all review flows: run(diff, pr_desc, config) -> findings
"""

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.transcript_logger import TranscriptLogger

logger = logging.getLogger(__name__)


@dataclass
class Finding:
    """Structured defect finding"""
    id: str = ""
    category: str = ""
    severity: str = "medium"
    title: str = ""
    description: str = ""
    file_path: str = ""
    line_range: str = ""
    evidence: str = ""
    suggestion: str = ""
    confidence: float = 0.5
    spec_reference: str = ""
    sources: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class ReviewResult:
    """Complete review result container"""
    flow_mode: str = ""
    findings: List[Finding] = field(default_factory=list)
    summary: str = ""
    duration_seconds: float = 0.0
    offline: bool = False
    metadata: dict = field(default_factory=dict)
    transcript: object = None  # TranscriptLogger
    evidence_store_path: str = ""  # EvidenceStore 持久化路径（v2 新增）

    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return {
            "flow_mode": self.flow_mode,
            "findings": [
                {k: v for k, v in f.__dict__.items() if v}
                for f in self.findings
            ],
            "summary": self.summary,
            "duration_seconds": round(self.duration_seconds, 2),
            "offline": self.offline,
            "metadata": self.metadata,
            "evidence_store_path": self.evidence_store_path,
        }


def finding_to_dict(f: Finding) -> dict:
    """Serialize a Finding to a compact dict (drop empty fields)."""
    return {k: v for k, v in f.__dict__.items() if v}


def findings_to_json(findings: list[Finding]) -> str:
    """Serialize a list of Findings to a JSON string for prompt injection."""
    return json.dumps(
        [finding_to_dict(f) for f in findings],
        ensure_ascii=False,
        indent=2,
    )


def apply_debate_actions(
    findings: list[Finding],
    actions: list[dict],
    new_findings: list[dict],
) -> list[Finding]:
    """
    Apply debate actions directly to a list of Finding objects.

    Actions:
      - ACCEPT:     no-op (finding is kept as-is)
      - CHALLENGE:  no-op (flagged but retained; Debater should follow up)
      - DOWNGRADE:  mutate finding.severity
      - MERGE:      merge source into target, remove source
      - REJECT:     remove finding from list

    Returns a new list of Finding objects.
    """
    # Build id -> index lookup
    id_index: dict[str, int] = {}
    for i, f in enumerate(findings):
        if f.id:
            id_index[f.id] = i

    # Track which indices to remove (REJECT / merge-sources)
    remove_indices: set[int] = set()

    for action in actions:
        if not isinstance(action, dict):
            continue
        fid = action.get("finding_id", "")
        act = action.get("action", "").upper()
        idx = id_index.get(fid)
        if idx is None:
            logger.warning(f"Debate action references unknown finding: {fid}")
            continue

        if act == "ACCEPT":
            pass  # keep as-is

        elif act == "CHALLENGE":
            # Attach challenge reason to metadata; keep finding
            reason = action.get("reason", "")
            if reason:
                existing = findings[idx].metadata.get("challenges", [])
                existing.append(reason)
                findings[idx].metadata["challenges"] = existing

        elif act == "DOWNGRADE":
            new_sev = action.get("new_severity", "").lower()
            if new_sev in ("critical", "high", "medium", "low", "info"):
                old = findings[idx].severity
                findings[idx].severity = new_sev
                logger.info(f"DOWNGRADE {fid}: {old} -> {new_sev}")
            else:
                logger.warning(f"DOWNGRADE {fid}: invalid severity '{new_sev}'")

        elif act == "MERGE":
            target_id = action.get("merge_target_id", "")
            target_idx = id_index.get(target_id)
            if target_idx is None:
                logger.warning(f"MERGE {fid}: target {target_id} not found")
                continue
            # Merge source into target: keep highest severity, append evidence
            src = findings[idx]
            tgt = findings[target_idx]
            sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
            if sev_order.get(src.severity, 9) < sev_order.get(tgt.severity, 9):
                tgt.severity = src.severity
            if src.evidence and src.evidence not in tgt.evidence:
                tgt.evidence = f"{tgt.evidence}\n---\n{src.evidence}" if tgt.evidence else src.evidence
            if src.description and src.description not in tgt.description:
                tgt.description = f"{tgt.description}\n[Merged from {fid}] {src.description}"
            tgt.confidence = max(tgt.confidence, src.confidence)
            if src.sources:
                tgt.sources = list(set(tgt.sources + src.sources))
            remove_indices.add(idx)
            logger.info(f"MERGE {fid} -> {target_id}")

        elif act == "REJECT":
            remove_indices.add(idx)
            logger.info(f"REJECT {fid}: {action.get('reason', '')}")

        else:
            logger.warning(f"Unknown debate action: {act} for {fid}")

    # Build surviving findings
    result = [f for i, f in enumerate(findings) if i not in remove_indices]

    # Append genuinely new findings from debate
    for item in new_findings:
        if isinstance(item, dict) and item.get("title"):
            # Avoid duplicates by title
            existing_titles = {f.title for f in result}
            if item["title"] not in existing_titles:
                result.append(Finding(
                    id=item.get("id", f"NEW-{len(result)+1}"),
                    category=item.get("category", "debate"),
                    severity=item.get("severity", "medium"),
                    title=item.get("title", ""),
                    description=item.get("description", ""),
                    file_path=item.get("file_path", ""),
                    line_range=item.get("line_range", ""),
                    evidence=item.get("evidence", ""),
                    suggestion=item.get("suggestion", ""),
                    confidence=item.get("confidence", 0.5),
                    sources=["debate"],
                ))

    return result


class BaseFlow(ABC):
    """
    Abstract base class for all review flows.
    Subclasses implement run() with specific orchestration logic.
    """

    def __init__(self, logger_instance: Optional[Any] = None, transcript: TranscriptLogger | None = None):
        self._logger = logger_instance or logger
        self._task_id: str = ""
        self.transcript = transcript or TranscriptLogger()

    @property
    def flow_mode(self) -> str:
        """Return the flow mode identifier"""
        return self.__class__.__name__.lower().replace("flow", "")

    async def execute(
        self,
        diff: str,
        pr_description: str = "",
        config: Optional[Dict] = None,
    ) -> ReviewResult:
        """
        Execute the review flow with timing and error handling.
        :param diff: Code diff content
        :param pr_description: PR description
        :param config: Additional configuration
        :return: ReviewResult with findings
        """
        config = config or {}
        start_time = time.time()
        self._logger.info(f"Starting {self.flow_mode} flow")

        try:
            result = await self.run(diff, pr_description, config)
            result.flow_mode = self.flow_mode
            result.duration_seconds = time.time() - start_time
            result.transcript = self.transcript
            self._logger.info(
                f"{self.flow_mode} flow completed: "
                f"{len(result.findings)} findings in {result.duration_seconds:.1f}s"
            )
            return result
        except Exception as e:
            duration = time.time() - start_time
            self._logger.error(f"{self.flow_mode} flow failed after {duration:.1f}s: {e}")
            return ReviewResult(
                flow_mode=self.flow_mode,
                findings=[],
                summary=f"Flow failed: {e}",
                duration_seconds=duration,
            )

    @abstractmethod
    async def run(
        self,
        diff: str,
        pr_description: str,
        config: Dict,
    ) -> ReviewResult:
        """
        Core flow logic (implemented by subclasses).
        :param diff: Code diff
        :param pr_description: PR description
        :param config: Configuration dict
        :return: ReviewResult
        """
        pass

