"""
Judge Module Tests - PR-Review Agent
Test scoring, output format, offline behavior
"""

import json
import pytest
from pathlib import Path

from src.models.mimo_wrapper import create_mimo_model
from src.judge.judge_runner import JudgeRunner, JudgeScores, JudgeResult


class TestJudgeScores:
    """JudgeScores tests"""

    def test_total_score(self):
        scores = JudgeScores(
            critical_risk_coverage=80, evidence_quality=70,
            risk_accuracy=90, noise_control=60,
            actionability=75, report_clarity=85,
        )
        assert scores.total_score == 77

    def test_to_dict(self):
        scores = JudgeScores(critical_risk_coverage=80)
        d = scores.to_dict()
        assert d["critical_risk_coverage"] == 80
        assert "total_score" in d

    def test_zero_scores(self):
        scores = JudgeScores()
        assert scores.total_score == 0


class TestJudgeResult:
    """JudgeResult tests"""

    def test_to_dict(self):
        result = JudgeResult(
            scores=JudgeScores(critical_risk_coverage=80),
            strengths=["good coverage"],
            offline=True,
        )
        d = result.to_dict()
        assert d["scores"]["critical_risk_coverage"] == 80
        assert d["offline"] is True
        assert "good coverage" in d["evaluation"]["strengths"]

    def test_to_markdown(self):
        result = JudgeResult(
            scores=JudgeScores(
                critical_risk_coverage=80, evidence_quality=70,
                risk_accuracy=90, noise_control=60,
                actionability=75, report_clarity=85,
            ),
            strengths=["Comprehensive security scan"],
            weaknesses=["Some false positives"],
            suggestions=["Add more test coverage"],
        )
        md = result.to_markdown()
        assert "# AI Judge Evaluation" in md
        assert "77/100" in md
        assert "Comprehensive security scan" in md
        assert "Some false positives" in md

    def test_to_markdown_offline(self):
        result = JudgeResult(offline=True)
        md = result.to_markdown()
        assert "offline" in md.lower()


class TestJudgeRunner:
    """JudgeRunner tests"""

    def test_offline_runner(self):
        model = create_mimo_model(api_url="", api_key="")
        runner = JudgeRunner(model=model)
        assert runner.offline is True

    @pytest.mark.asyncio
    async def test_offline_run_returns_result(self):
        model = create_mimo_model(api_url="", api_key="")
        runner = JudgeRunner(model=model)
        judge_input = {
            "diff_summary": "test diff",
            "pr_description": "test pr",
            "findings": {"findings": [], "total_count": 0},
            "report_content": "test report",
        }
        result = await runner.run(judge_input)
        assert isinstance(result, JudgeResult)
        assert result.offline is True

    def test_save_result(self, tmp_path):
        model = create_mimo_model(api_url="", api_key="")
        runner = JudgeRunner(model=model)
        result = JudgeResult(scores=JudgeScores(critical_risk_coverage=50))
        paths = runner.save_result(result, str(tmp_path), task_id="test")
        assert Path(paths["json"]).exists()
        assert Path(paths["md"]).exists()
        # Verify JSON content
        data = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
        assert data["scores"]["critical_risk_coverage"] == 50
