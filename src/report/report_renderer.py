"""
Report Renderer - PR-Review Agent
Renders findings.json into report.md
Groups by severity, includes evidence, suggestions, spec references
"""

import logging
from datetime import datetime
from typing import List, Optional

from src.report.findings import FindingData, FindingsCollection, SEVERITY_ORDER

logger = logging.getLogger(__name__)

# Severity display config
SEVERITY_LABELS = {
    "critical": "⚠️ 严重 (CRITICAL)",
    "high": "⚠️ 高危 (HIGH)",
    "medium": "⚪ 中等 (MEDIUM)",
    "low": "⚪ 低危 (LOW)",
    "info": "ℹ️ 信息 (INFO)",
}

SEVERITY_EMOJI = {
    "critical": "⚠️",
    "high": "⚠️",
    "medium": "⚪",
    "low": "⚪",
    "info": "ℹ️",
}


class ReportRenderer:
    """
    Markdown report renderer.
    Renders FindingsCollection into a structured report.md.
    """

    def __init__(self, title: str = "PR 代码审查报告"):
        self.title = title

    def render(self, collection: FindingsCollection, flow_mode: str = "",
               duration: float = 0, summary_extra: str = "") -> str:
        """
        Render findings collection to Markdown report string.
        :param collection: FindingsCollection
        :param flow_mode: Review flow mode name
        :param duration: Review duration in seconds
        :param summary_extra: Additional summary text
        :return: Markdown string
        """
        lines = []
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Header
        lines.append(f"# {self.title}")
        lines.append("")
        lines.append(f"**生成时间**: {now}")
        if flow_mode:
            lines.append(f"**审查模式**: {flow_mode}")
        if duration > 0:
            lines.append(f"**耗时**: {duration:.1f}秒")
        lines.append("")

        # Summary
        counts = collection.count_by_severity()
        lines.append("## 摘要")
        lines.append("")
        lines.append(f"发现总数：**{collection.count}**")
        lines.append("")
        lines.append("| 严重程度 | 数量 |")
        lines.append("|------|------|")
        for sev in ["critical", "high", "medium", "low", "info"]:
            if counts.get(sev, 0) > 0:
                label = SEVERITY_LABELS.get(sev, sev)
                lines.append(f"| {label} | {counts[sev]} |")
        lines.append("")
        if summary_extra:
            lines.append(summary_extra)
            lines.append("")

        # Findings grouped by severity
        sorted_findings = collection.sorted_by_severity()
        current_severity = None

        for f in sorted_findings:
            if f.severity != current_severity:
                current_severity = f.severity
                label = SEVERITY_LABELS.get(f.severity, f.severity.upper())
                lines.append(f"## {label} 级别发现")
                lines.append("")

            lines.append(f"### {f.id}: {f.title}")
            lines.append("")
            lines.append(f"- **类别**: {f.category}")
            lines.append(f"- **文件**: `{f.file_path}` (第 {f.line_range} 行)")
            lines.append(f"- **置信度**: {f.confidence:.0%}")
            if f.spec_reference:
                lines.append(f"- **规范引用**: {f.spec_reference}")
            lines.append("")
            lines.append(f"**描述**: {f.description}")
            lines.append("")
            if f.evidence:
                lines.append("**证据**：")
                lines.append("```")
                lines.append(f.evidence[:500])
                lines.append("```")
                lines.append("")
            if f.suggestion:
                lines.append(f"**修复建议**: {f.suggestion}")
                lines.append("")
            lines.append("---")
            lines.append("")

        # Footer
        lines.append("## 附录")
        lines.append("")
        lines.append(f"- 报告由 PR-Review Agent 生成")
        lines.append(f"- 发现总数：{collection.count}")
        lines.append("")

        return "\n".join(lines)

    def render_judge_input(self, collection: FindingsCollection,
                           diff: str = "", pr_description: str = "",
                           report_content: str = "") -> dict:
        """
        Generate judge_input.json structure for AI Judge.
        :return: dict ready for JSON serialization
        """
        return {
            "diff_summary": diff[:2000] if diff else "",
            "pr_description": pr_description,
            "findings": collection.to_dict(),
            "report_content": report_content[:5000] if report_content else "",
            "total_findings": collection.count,
            "severity_counts": collection.count_by_severity(),
        }

    def render_from_evidence_store(
        self, evidence_store_dict: dict, flow_mode: str = "", duration: float = 0.0
    ) -> str:
        """
        v2 兼容方法：从 EvidenceStore 字典渲染报告。
        支持新数据结构（含 policy_references、challenges、decisions）。
        作为 ReportWriterAgent 的离线降级方案。
        :param evidence_store_dict: EvidenceStore.to_dict() 的输出
        :param flow_mode: 流程模式标识
        :param duration: 审查耗时（秒）
        :return: Markdown 格式的报告字符串
        """
        from src.report.findings import FindingsCollection, FindingData

        # 将 EvidenceStore 中的 findings 转换为 FindingsCollection
        collection = FindingsCollection()
        for item in evidence_store_dict.get("findings", []):
            fd = FindingData(
                id=item.get("id", ""),
                category=item.get("category", ""),
                severity=item.get("severity", "medium"),
                title=item.get("title", ""),
                description=item.get("description", ""),
                file_path=item.get("file_path", ""),
                line_range=item.get("line_range", ""),
                evidence=item.get("evidence", ""),
                suggestion=item.get("suggestion", ""),
                confidence=item.get("confidence", 0.5),
                spec_reference=item.get("spec_reference", ""),
            )
            collection.add(fd)

        # 使用现有渲染器生成基础报告
        report = self.render(collection, flow_mode=flow_mode, duration=duration)

        # 追加 policy_references 章节（模板渲染器原本不支持）
        policy_refs = evidence_store_dict.get("policy_references", [])
        if policy_refs:
            report += "\n## 公司规范引用\n\n"
            for ref in policy_refs:
                label = ref.get("policy_label", "")
                rule = ref.get("rule_text", "")[:200]
                report += f"- **{label}**：{rule}\n"
            report += "\n"

        # 追加裁决记录摘要
        decisions = evidence_store_dict.get("decisions", [])
        if decisions:
            report += "\n## 裁决记录\n\n"
            report += f"共 {len(decisions)} 条裁决：\n\n"
            for d in decisions:
                report += f"- [{d.get('action', '')}] {d.get('finding_id', '')}：{d.get('reason', '')[:100]}\n"
            report += "\n"

        return report
