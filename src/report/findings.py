"""
Findings Data Management - PR-Review Agent
Structured defect data read/write and validation
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# Severity level ordering (for sorting)
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


@dataclass
class FindingData:
    """Structured defect data"""
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

    def validate(self) -> List[str]:
        """Validate finding data, return list of error messages"""
        errors = []
        if not self.title:
            errors.append("title is required")
        if self.severity not in SEVERITY_ORDER:
            errors.append(f"severity must be one of {list(SEVERITY_ORDER.keys())}")
        if not (0 <= self.confidence <= 1):
            errors.append("confidence must be between 0 and 1")
        return errors


@dataclass
class FindingsCollection:
    """Collection of findings with read/write capabilities"""
    findings: List[FindingData] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def add(self, finding: FindingData) -> None:
        self.findings.append(finding)

    def add_batch(self, findings: List[FindingData]) -> None:
        self.findings.extend(findings)

    @property
    def count(self) -> int:
        return len(self.findings)

    def count_by_severity(self) -> dict:
        """Count findings by severity level"""
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for f in self.findings:
            if f.severity in counts:
                counts[f.severity] += 1
        return counts

    def sorted_by_severity(self) -> List[FindingData]:
        """Return findings sorted by severity (critical first)"""
        return sorted(
            self.findings,
            key=lambda f: SEVERITY_ORDER.get(f.severity, 99)
        )

    def filter_by_severity(self, min_severity: str = "info") -> List[FindingData]:
        """Filter findings by minimum severity level"""
        min_level = SEVERITY_ORDER.get(min_severity, 4)
        return [f for f in self.findings if SEVERITY_ORDER.get(f.severity, 99) <= min_level]

    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return {
            "findings": [asdict(f) for f in self.findings],
            "total_count": self.count,
            "severity_counts": self.count_by_severity(),
            "metadata": self.metadata,
        }

    def save_json(self, filepath: str) -> None:
        """Save findings to JSON file"""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        logger.info(f"Findings saved: {self.count} items -> {filepath}")

    @classmethod
    def load_json(cls, filepath: str) -> "FindingsCollection":
        """Load findings from JSON file"""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Findings file not found: {filepath}")
        data = json.loads(path.read_text(encoding="utf-8"))
        collection = cls(metadata=data.get("metadata", {}))
        for item in data.get("findings", []):
            collection.add(FindingData(**{k: v for k, v in item.items()
                                          if k in FindingData.__dataclass_fields__}))
        return collection

    @classmethod
    def from_review_findings(cls, findings: list) -> "FindingsCollection":
        """Create from list of Finding objects (from flows)"""
        collection = cls()
        for f in findings:
            fd = FindingData(
                id=getattr(f, "id", ""),
                category=getattr(f, "category", ""),
                severity=getattr(f, "severity", "medium"),
                title=getattr(f, "title", ""),
                description=getattr(f, "description", ""),
                file_path=getattr(f, "file_path", ""),
                line_range=getattr(f, "line_range", ""),
                evidence=getattr(f, "evidence", ""),
                suggestion=getattr(f, "suggestion", ""),
                confidence=getattr(f, "confidence", 0.5),
                spec_reference=getattr(f, "spec_reference", ""),
                sources=getattr(f, "sources", []),
                metadata=getattr(f, "metadata", {}),
            )
            collection.add(fd)
        return collection
