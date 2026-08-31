"""
Flows 单元测试 - PR-Review Agent v2
测试 SimpleFlow、基础数据结构、v2 新增的 flow 组件
"""

import pytest
from src.flows.base_flow import Finding, ReviewResult, BaseFlow
from src.flows.simple_flow import SimpleFlow
from src.flows.evidence_store import EvidenceStore


class TestFinding:
    """Finding 数据类测试"""

    def test_finding_creation(self):
        """创建 Finding"""
        f = Finding(id="SEC-001", category="security", severity="high", title="test")
        assert f.id == "SEC-001"
        assert f.severity == "high"

    def test_review_result_to_dict(self):
        """ReviewResult 序列化"""
        result = ReviewResult(
            flow_mode="simple",
            findings=[Finding(id="1", title="test")],
            summary="found 1 issue",
            duration_seconds=1.5,
        )
        d = result.to_dict()
        assert d["flow_mode"] == "simple"
        assert len(d["findings"]) == 1
        assert d["duration_seconds"] == 1.5

    def test_review_result_has_evidence_store_path(self):
        """v2: ReviewResult 应有 evidence_store_path 字段"""
        result = ReviewResult()
        assert hasattr(result, "evidence_store_path")
        assert result.evidence_store_path == ""


class TestSimpleFlow:
    """Simple 离线流程测试"""

    @pytest.mark.asyncio
    async def test_detects_hardcoded_password(self):
        """检测硬编码密码"""
        flow = SimpleFlow()
        diff = "+++ b/config.py\n+ password = 'secret123'\n"
        result = await flow.execute(diff)
        assert len(result.findings) > 0
        categories = [f.category for f in result.findings]
        assert "security" in categories

    @pytest.mark.asyncio
    async def test_detects_sql_injection(self):
        """检测 SQL 注入"""
        flow = SimpleFlow()
        diff = '+++ b/db.py\n+ query = "SELECT * FROM users WHERE id = " + user_id\n'
        result = await flow.execute(diff)
        security_findings = [f for f in result.findings if f.category == "security"]
        assert len(security_findings) > 0

    @pytest.mark.asyncio
    async def test_detects_eval_usage(self):
        """检测 eval() 使用"""
        flow = SimpleFlow()
        diff = "+++ b/utils.py\n+ result = eval(user_input)\n"
        result = await flow.execute(diff)
        titles = [f.title for f in result.findings]
        assert any("eval" in t.lower() for t in titles)

    @pytest.mark.asyncio
    async def test_empty_diff_returns_no_findings(self):
        """空 diff 应返回空 findings"""
        flow = SimpleFlow()
        result = await flow.execute("")
        assert len(result.findings) == 0
