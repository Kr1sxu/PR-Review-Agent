"""
Council v2 流程测试 - PR-Review Agent v2
测试程序化合并、流程创建（端到端测试需要真实模型，此处只测可测部分）
"""

import pytest
from src.flows.council_flow import CouncilFlow
from src.flows.base_flow import Finding


class TestProgrammaticMerge:
    """程序化去重合并测试"""

    def test_no_duplicates(self):
        """无重复 findings 应全部保留"""
        findings = [
            Finding(id="1", title="问题A", file_path="a.py", severity="high"),
            Finding(id="2", title="完全不同的问题", file_path="b.py", severity="low"),
        ]
        merged = CouncilFlow._programmatic_merge(findings)
        assert len(merged) == 2

    def test_merge_similar_findings(self):
        """相似 findings 应被合并"""
        findings = [
            Finding(id="1", title="SQL注入漏洞", file_path="db.py",
                    severity="medium", evidence="证据A", confidence=0.6),
            Finding(id="2", title="SQL注入漏洞", file_path="db.py",
                    severity="high", evidence="更详细的证据B", confidence=0.8),
        ]
        merged = CouncilFlow._programmatic_merge(findings)
        assert len(merged) == 1
        assert merged[0].severity == "high"  # 保留更高严重级别
        assert "证据B" in merged[0].evidence  # 保留更长证据

    def test_merge_preserves_sources(self):
        """合并应保留所有来源"""
        findings = [
            Finding(id="1", title="重复问题", file_path="x.py",
                    sources=["security_expert"]),
            Finding(id="2", title="重复问题", file_path="x.py",
                    sources=["logic_reviewer"]),
        ]
        merged = CouncilFlow._programmatic_merge(findings)
        assert len(merged) == 1
        assert "security_expert" in merged[0].sources
        assert "logic_reviewer" in merged[0].sources

    def test_different_files_not_merged(self):
        """不同文件的相似标题不应合并"""
        findings = [
            Finding(id="1", title="空指针风险", file_path="a.py"),
            Finding(id="2", title="空指针风险", file_path="b.py"),
        ]
        merged = CouncilFlow._programmatic_merge(findings)
        assert len(merged) == 2

    def test_severity_sorting(self):
        """合并结果应按严重级别排序"""
        findings = [
            Finding(id="1", title="低危问题", file_path="a.py", severity="low"),
            Finding(id="2", title="高危问题", file_path="b.py", severity="critical"),
            Finding(id="3", title="中危问题", file_path="c.py", severity="medium"),
        ]
        merged = CouncilFlow._programmatic_merge(findings)
        assert merged[0].severity == "critical"
        assert merged[1].severity == "medium"
        assert merged[2].severity == "low"

    def test_parse_findings_from_json_array(self):
        """从 JSON 数组文本解析 findings"""
        text = '[{"id":"SEC-001","category":"security","severity":"high","title":"SQL注入"}]'
        findings = CouncilFlow._parse_findings(text)
        assert len(findings) == 1
        assert findings[0].id == "SEC-001"

    def test_parse_findings_from_dict_with_key(self):
        """从带 merged_findings 键的 dict 解析"""
        text = '{"merged_findings":[{"id":"Q-001","title":"问题1"}]}'
        findings = CouncilFlow._parse_findings(text)
        assert len(findings) == 1

    def test_parse_empty_input(self):
        """空输入应返回空列表"""
        assert CouncilFlow._parse_findings("") == []
        assert CouncilFlow._parse_findings("[]") == []
