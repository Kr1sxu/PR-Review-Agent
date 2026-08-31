"""
Report Module Tests - PR-Review Agent
Test findings data management, JSON I/O, report rendering
"""

import json
import pytest
from pathlib import Path

from src.report.findings import FindingData, FindingsCollection
from src.report.report_renderer import ReportRenderer


class TestFindingData:
    """FindingData tests"""

    def test_creation(self):
        f = FindingData(id="SEC-001", category="security", severity="high",
                        title="SQL injection")
        assert f.id == "SEC-001"
        assert f.severity == "high"

    def test_validate_valid(self):
        f = FindingData(title="test", severity="high", confidence=0.8)
        errors = f.validate()
        assert errors == []

    def test_validate_missing_title(self):
        f = FindingData(severity="high")
        errors = f.validate()
        assert any("title" in e for e in errors)

    def test_validate_bad_severity(self):
        f = FindingData(title="test", severity="critical_high")
        errors = f.validate()
        assert any("severity" in e for e in errors)

    def test_validate_bad_confidence(self):
        f = FindingData(title="test", severity="high", confidence=1.5)
        errors = f.validate()
        assert any("confidence" in e for e in errors)


class TestFindingsCollection:
    """FindingsCollection tests"""

    def test_add_and_count(self):
        c = FindingsCollection()
        c.add(FindingData(id="1", title="a", severity="high"))
        c.add(FindingData(id="2", title="b", severity="low"))
        assert c.count == 2

    def test_count_by_severity(self):
        c = FindingsCollection()
        c.add(FindingData(title="a", severity="critical"))
        c.add(FindingData(title="b", severity="high"))
        c.add(FindingData(title="c", severity="high"))
        c.add(FindingData(title="d", severity="info"))
        counts = c.count_by_severity()
        assert counts["critical"] == 1
        assert counts["high"] == 2
        assert counts["info"] == 1

    def test_sorted_by_severity(self):
        c = FindingsCollection()
        c.add(FindingData(title="low", severity="low"))
        c.add(FindingData(title="critical", severity="critical"))
        c.add(FindingData(title="medium", severity="medium"))
        sorted_f = c.sorted_by_severity()
        assert sorted_f[0].severity == "critical"
        assert sorted_f[-1].severity == "low"

    def test_filter_by_severity(self):
        c = FindingsCollection()
        c.add(FindingData(title="c", severity="critical"))
        c.add(FindingData(title="h", severity="high"))
        c.add(FindingData(title="m", severity="medium"))
        c.add(FindingData(title="i", severity="info"))
        filtered = c.filter_by_severity("high")
        assert len(filtered) == 2

    def test_save_and_load_json(self, tmp_path):
        path = str(tmp_path / "findings.json")
        c = FindingsCollection()
        c.add(FindingData(id="1", title="test", severity="high", confidence=0.9))
        c.save_json(path)

        loaded = FindingsCollection.load_json(path)
        assert loaded.count == 1
        assert loaded.findings[0].title == "test"

    def test_load_nonexistent(self):
        with pytest.raises(FileNotFoundError):
            FindingsCollection.load_json("/nonexistent/path.json")

    def test_to_dict(self):
        c = FindingsCollection()
        c.add(FindingData(id="1", title="test"))
        d = c.to_dict()
        assert "findings" in d
        assert "total_count" in d
        assert d["total_count"] == 1

    def test_from_review_findings(self):
        from src.flows.base_flow import Finding
        findings = [Finding(id="1", title="test", severity="high")]
        c = FindingsCollection.from_review_findings(findings)
        assert c.count == 1
        assert c.findings[0].title == "test"


class TestReportRenderer:
    """Report renderer tests"""

    def test_render_basic(self):
        c = FindingsCollection()
        c.add(FindingData(id="SEC-001", category="security", severity="high",
                          title="SQL injection", file_path="db.py",
                          line_range="10", evidence="query = ... + input",
                          suggestion="Use parameterized queries"))
        renderer = ReportRenderer()
        report = renderer.render(c, flow_mode="council", duration=5.0)
        assert "# PR Code Review Report" in report
        assert "SQL injection" in report
        assert "council" in report
        assert "HIGH" in report

    def test_render_empty(self):
        c = FindingsCollection()
        renderer = ReportRenderer()
        report = renderer.render(c)
        assert "Total findings: **0**" in report

    def test_render_groups_by_severity(self):
        c = FindingsCollection()
        c.add(FindingData(id="1", title="critical issue", severity="critical"))
        c.add(FindingData(id="2", title="low issue", severity="low"))
        renderer = ReportRenderer()
        report = renderer.render(c)
        crit_pos = report.find("CRITICAL")
        low_pos = report.find("LOW")
        assert crit_pos < low_pos

    def test_render_judge_input(self):
        c = FindingsCollection()
        c.add(FindingData(id="1", title="test"))
        renderer = ReportRenderer()
        ji = renderer.render_judge_input(c, diff="some diff", pr_description="desc")
        assert "findings" in ji
        assert ji["diff_summary"] == "some diff"
        assert ji["total_findings"] == 1
