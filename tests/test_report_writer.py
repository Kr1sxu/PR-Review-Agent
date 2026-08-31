"""
ReportWriterAgent 单元测试 - PR-Review Agent v2
测试 Agent 创建、降级渲染
"""

import pytest
from src.agents.report_writer import (
    create_report_writer_agent,
    fallback_render,
)
from src.flows.evidence_store import EvidenceStore, PolicyReference
from src.flows.base_flow import Finding
from agentscope.agent._agent import Agent
from src.models.mimo_wrapper import create_mimo_model


@pytest.fixture
def offline_model():
    """创建离线模型用于测试"""
    return create_mimo_model(api_url="", api_key="")


@pytest.fixture
def sample_evidence_store_dict():
    """构造测试用的 EvidenceStore 字典"""
    store = EvidenceStore(task_id="test-report")
    store.findings = [
        Finding(
            id="SEC-001", category="security", severity="high",
            title="SQL注入风险", description="查询使用字符串拼接",
            file_path="db.py", line_range="42",
            evidence="SELECT * FROM users WHERE id=" + "x",
            suggestion="使用参数化查询", confidence=0.9,
        ),
        Finding(
            id="QUA-002", category="quality", severity="low",
            title="裸 except", description="异常处理过于宽泛",
            file_path="app.py", line_range="100",
            confidence=0.7,
        ),
    ]
    store.policy_references = [
        PolicyReference(
            policy_id="POL-001", policy_area="sql_injection",
            policy_label="SQL 注入风险",
            rule_text="所有数据库查询必须使用参数化语句",
            matched_finding_ids=["SEC-001"],
        ),
    ]
    return store.to_dict()


class TestReportWriterCreation:
    """ReportWriterAgent 创建测试"""

    def test_create_agent(self, offline_model):
        """创建 ReportWriterAgent"""
        agent = create_report_writer_agent(offline_model)
        assert isinstance(agent, Agent)
        assert agent.name == "report_writer"


class TestFallbackRender:
    """离线降级渲染测试"""

    def test_fallback_generates_report(self, sample_evidence_store_dict):
        """降级渲染应生成有效 Markdown 报告"""
        report = fallback_render(sample_evidence_store_dict, flow_mode="council", duration=10.5)
        assert len(report) > 0
        assert "SQL注入风险" in report or "SQL" in report
        assert "council" in report or "Council" in report

    def test_fallback_includes_policy_references(self, sample_evidence_store_dict):
        """降级渲染应包含公司规范引用"""
        report = fallback_render(sample_evidence_store_dict)
        assert "公司规范引用" in report
        assert "SQL 注入风险" in report or "参数化" in report

    def test_fallback_includes_decisions(self, sample_evidence_store_dict):
        """降级渲染应包含裁决记录"""
        # 添加裁决到字典
        sample_evidence_store_dict["decisions"] = [
            {"finding_id": "SEC-001", "action": "ACCEPT", "reason": "证据充分"},
        ]
        report = fallback_render(sample_evidence_store_dict)
        assert "裁决记录" in report

    def test_fallback_empty_findings(self):
        """空 findings 应生成有效报告"""
        store = EvidenceStore()
        report = fallback_render(store.to_dict())
        assert len(report) > 0
