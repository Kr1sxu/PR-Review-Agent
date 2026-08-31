"""
Judge Runner - PR-Review Agent
Runs AI Judge evaluation on review results
Outputs judge.json + judge.md, six-dimension scoring data
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from agentscope.message._base import Msg
from agentscope.model._base import ChatModelBase
from src.core.transcript_logger import TranscriptLogger

logger = logging.getLogger(__name__)


@dataclass
class JudgeScores:
    """Six-dimension judge scores (0-100 each)"""
    critical_risk_coverage: int = 0
    evidence_quality: int = 0
    risk_accuracy: int = 0
    noise_control: int = 0
    actionability: int = 0
    report_clarity: int = 0

    @property
    def total_score(self) -> int:
        scores = [
            self.critical_risk_coverage, self.evidence_quality,
            self.risk_accuracy, self.noise_control,
            self.actionability, self.report_clarity,
        ]
        return round(sum(scores) / len(scores)) if scores else 0

    def to_dict(self) -> dict:
        return {
            "critical_risk_coverage": self.critical_risk_coverage,
            "evidence_quality": self.evidence_quality,
            "risk_accuracy": self.risk_accuracy,
            "noise_control": self.noise_control,
            "actionability": self.actionability,
            "report_clarity": self.report_clarity,
            "total_score": self.total_score,
        }


@dataclass
class JudgeResult:
    """Complete judge evaluation result"""
    scores: JudgeScores = field(default_factory=JudgeScores)
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    raw_response: str = ""
    transcript: object = None  # TranscriptLogger instance
    offline: bool = False
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "scores": self.scores.to_dict(),
            "evaluation": {
                "strengths": self.strengths,
                "weaknesses": self.weaknesses,
                "suggestions": self.suggestions,
            },
            "offline": self.offline,
            "duration_seconds": round(self.duration_seconds, 2),
        }

    def to_markdown(self) -> str:
        """Render judge result as Markdown"""
        lines = ["# AI 评审结果", ""]
        lines.append(f"**总分**: {self.scores.total_score}/100")
        lines.append("")
        lines.append("## 六维评分")
        lines.append("")
        lines.append("| 评分维度 | 分数 |")
        lines.append("|------|------|")
        labels = {
            "critical_risk_coverage": "关键风险覆盖",
            "evidence_quality": "证据质量",
            "risk_accuracy": "风险准确度",
            "noise_control": "噪声控制",
            "actionability": "可操作性",
            "report_clarity": "报告清晰度",
        }
        for key, label in labels.items():
            score = getattr(self.scores, key, 0)
            lines.append(f"| {label} | {score}/100 |")
        lines.append("")

        if self.strengths:
            lines.append("## 优点")
            for s in self.strengths:
                lines.append(f"- {s}")
            lines.append("")

        if self.weaknesses:
            lines.append("## 不足")
            for w in self.weaknesses:
                lines.append(f"- {w}")
            lines.append("")

        if self.suggestions:
            lines.append("## 改进建议")
            for s in self.suggestions:
                lines.append(f"- {s}")
            lines.append("")

        if self.offline:
            lines.append("> **注意**: 评审以离线模式运行（未连接模型）")
            lines.append("")

        return "\n".join(lines)


class JudgeRunner:
    """
    AI Judge evaluation runner.
    - Reads judge_input data (report summary + structured findings)
    - Runs independent Judge agent session
    - Outputs JudgeResult with six-dimension scores
    """

    def __init__(self, model: ChatModelBase):
        self.model = model
        self.offline = getattr(model, "offline", False)

    async def run(self, judge_input: dict) -> JudgeResult:
        """
        Execute AI Judge evaluation.
        :param judge_input: dict with diff_summary, pr_description, findings, report_content
        :return: JudgeResult with scores and evaluation
        """
        import time
        import uuid
        from agentscope.model._base import ChatResponse, TextBlock, FinishedReason
        from datetime import datetime, timezone

        start = time.time()

        # Build judge prompt
        prompt = self._build_prompt(judge_input)

        # Create transcript logger
        transcript = TranscriptLogger()

        # Call model
        if self.offline:
            response = self._build_offline_response()
        else:
            try:
                msg = Msg(name="user", role="user",
                          content=[TextBlock(text=prompt)])
                call_start = time.time()
                response = await self.model._call_api(self.model.model, [msg])
                call_ms = int((time.time() - call_start) * 1000)
                transcript.log(
                    step="judge", agent="AI_Judge", action="call",
                    input_text=prompt,
                    output_text=",".join(
                        b.text for b in response.content
                        if isinstance(b, TextBlock)
                    ),
                    duration_ms=call_ms,
                    metadata={"model": getattr(self.model, "model_name", "unknown")},
                )
            except Exception as e:
                logger.warning(f"Judge model call failed: {e}")
                response = self._build_offline_response()
                transcript.log(
                    step="judge", agent="AI_Judge", action="error",
                    input_text=prompt, output_text=str(e),
                    metadata={"offline_fallback": True},
                )

        # Parse response
        text = ""
        for block in response.content:
            if isinstance(block, TextBlock):
                text += block.text

        result = self._parse_result(text)
        result.duration_seconds = time.time() - start
        result.raw_response = text
        result.offline = self.offline
        result.transcript = transcript
        return result

    def _build_prompt(self, judge_input: dict) -> str:
        diff = judge_input.get("diff_summary", "")
        pr_desc = judge_input.get("pr_description", "")
        findings = judge_input.get("findings", {})
        report = judge_input.get("report_content", "")


        # v2：提取 policy_references（如有），注入到 prompt 中供 Judge 参考
        policy_refs = judge_input.get('policy_references', [])
        policy_text = ''
        if policy_refs:
            policy_text = '\n\n## 公司规范引用\n'
            for ref in policy_refs[:10]:
                label = ref.get('policy_label', '')
                rule = ref.get('rule_text', '')[:200]
                policy_text += f'- {label}：{rule}\n'

        return f"""你是一位专业的代码审查质量评估专家（AI评审）。

## 代码变更 (Diff)
{diff[:3000]}

## PR 描述
{pr_desc[:500]}

## 审查发现 (JSON)
{json.dumps(findings, ensure_ascii=False)[:3000]}
{policy_text}

## 报告内容
{report[:3000]}

请对审查报告进行六维评分（每项0-100分）：
1. 关键风险覆盖
2. 证据质量
3. 风险准确度
4. 噪声控制
5. 可操作性
6. 报告清晰度

请输出JSON对象，包含：
- scores：{{critical_risk_coverage, evidence_quality, risk_accuracy, noise_control, actionability, report_clarity}}
- evaluation：{{strengths: [], weaknesses: [], suggestions: []}}
"""

    def _build_offline_response(self):
        from agentscope.model._base import ChatResponse, TextBlock, FinishedReason
        import uuid
        from datetime import datetime, timezone

        mock = json.dumps({
            "scores": {"critical_risk_coverage": 0, "evidence_quality": 0,
                       "risk_accuracy": 0, "noise_control": 0,
                       "actionability": 0, "report_clarity": 0},
            "evaluation": {"strengths": [], "weaknesses": ["离线模式 - 未连接模型"],
                           "suggestions": ["请连接 MiMo API 以获取真实评审"]},
        }, ensure_ascii=False)
        return ChatResponse(
            content=[TextBlock(text=mock)],
            is_last=True,
            id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc).isoformat(),
            finished_reason=FinishedReason.COMPLETED,
            metadata={"offline": True},
        )

    def _parse_result(self, text: str) -> JudgeResult:
        from src.models.mimo_wrapper import MiMoChatModel
        parsed = MiMoChatModel.extract_json(text)
        if not parsed or not isinstance(parsed, dict):
            return JudgeResult()

        scores_dict = parsed.get("scores", {})
        eval_dict = parsed.get("evaluation", {})

        scores = JudgeScores(
            critical_risk_coverage=scores_dict.get("critical_risk_coverage", 0),
            evidence_quality=scores_dict.get("evidence_quality", 0),
            risk_accuracy=scores_dict.get("risk_accuracy", 0),
            noise_control=scores_dict.get("noise_control", 0),
            actionability=scores_dict.get("actionability", 0),
            report_clarity=scores_dict.get("report_clarity", 0),
        )
        return JudgeResult(
            scores=scores,
            strengths=eval_dict.get("strengths", []),
            weaknesses=eval_dict.get("weaknesses", []),
            suggestions=eval_dict.get("suggestions", []),
        )

    def save_result(
        self,
        result: JudgeResult,
        output_dir: str,
        task_id: str = "",
        judge_input: dict | None = None,
    ) -> dict:
        """Save judge result, judge_input.json, and judge_transcript.jsonl."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        prefix = f"{task_id}_" if task_id else ""

        # judge.json
        json_path = out / f"{prefix}judge.json"
        json_path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # judge.md
        md_path = out / f"{prefix}judge.md"
        md_path.write_text(result.to_markdown(), encoding="utf-8")

        saved = {"json": str(json_path), "md": str(md_path)}

        # judge_input.json
        if judge_input is not None:
            input_path = out / f"{prefix}judge_input.json"
            input_path.write_text(
                json.dumps(judge_input, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            saved["input"] = str(input_path)

        # judge_transcript.jsonl
        if result.transcript is not None and not result.transcript.empty:
            transcript_path = out / f"{prefix}judge_transcript.jsonl"
            result.transcript.save_jsonl(str(transcript_path))
            saved["transcript"] = str(transcript_path)

        logger.info(f"Judge results saved: {saved}")
        return saved

