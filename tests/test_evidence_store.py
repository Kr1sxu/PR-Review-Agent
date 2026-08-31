"""
EvidenceStore 单元测试 - PR-Review Agent v2
测试增删改查、持久化、加载、并发安全
"""

import pytest
import asyncio
import json
import tempfile
import os
from pathlib import Path

from src.flows.evidence_store import (
    EvidenceStore, PolicyReference, Challenge, Decision, DebateRound,
)
from src.flows.base_flow import Finding


class TestEvidenceStoreBasic:
    """基础增删改查测试"""

    def test_create_empty_store(self):
        """创建空 EvidenceStore"""
        store = EvidenceStore(task_id="test-001")
        assert store.task_id == "test-001"
        assert store.finding_count == 0
        assert store.is_empty

    @pytest.mark.asyncio
    async def test_add_finding(self):
        """添加单条 finding"""
        store = EvidenceStore()
        f = Finding(id="SEC-001", category="security", severity="high", title="SQL注入")
        await store.add_finding(f)
        assert store.finding_count == 1
        assert store.get_finding("SEC-001") is not None
        assert store.get_finding("SEC-001").title == "SQL注入"

    @pytest.mark.asyncio
    async def test_add_finding_dedup(self):
        """添加重复 id 的 finding 应覆盖而非追加"""
        store = EvidenceStore()
        f1 = Finding(id="SEC-001", title="旧版本")
        f2 = Finding(id="SEC-001", title="新版本")
        await store.add_finding(f1)
        await store.add_finding(f2)
        assert store.finding_count == 1
        assert store.get_finding("SEC-001").title == "新版本"

    @pytest.mark.asyncio
    async def test_batch_add_findings(self):
        """批量添加 findings"""
        store = EvidenceStore()
        findings = [
            Finding(id=f"F-{i}", title=f"缺陷 {i}")
            for i in range(5)
        ]
        await store.add_findings(findings)
        assert store.finding_count == 5

    @pytest.mark.asyncio
    async def test_remove_finding(self):
        """移除 finding"""
        store = EvidenceStore()
        await store.add_finding(Finding(id="SEC-001", title="测试"))
        assert store.finding_count == 1
        result = await store.remove_finding("SEC-001")
        assert result is True
        assert store.finding_count == 0
        assert store.get_finding("SEC-001") is None

    @pytest.mark.asyncio
    async def test_remove_nonexistent_finding(self):
        """移除不存在的 finding 应返回 False"""
        store = EvidenceStore()
        result = await store.remove_finding("NOTEXIST")
        assert result is False

    @pytest.mark.asyncio
    async def test_merge_findings(self):
        """合并两个 findings"""
        store = EvidenceStore()
        f1 = Finding(id="SEC-001", severity="medium", title="问题A",
                     evidence="证据1", confidence=0.6, sources=["reviewer_1"])
        f2 = Finding(id="SEC-002", severity="high", title="问题B",
                     evidence="证据2", confidence=0.8, sources=["reviewer_2"])
        await store.add_finding(f1)
        await store.add_finding(f2)

        success = await store.merge_findings("SEC-001", "SEC-002")
        assert success is True
        assert store.finding_count == 1
        merged = store.get_finding("SEC-002")
        assert merged.severity == "high"  # 保留更高严重级别
        assert merged.confidence == 0.8   # 保留更高置信度
        assert "证据1" in merged.evidence  # 合并证据

    @pytest.mark.asyncio
    async def test_merge_nonexistent_finding(self):
        """合不存在的 finding 应返回 False"""
        store = EvidenceStore()
        result = await store.merge_findings("NOTEXIST", "ALSO_NOTEXIST")
        assert result is False

    def test_get_findings_by_severity(self):
        """按严重级别筛选"""
        store = EvidenceStore()
        store.findings = [
            Finding(id="1", severity="high"),
            Finding(id="2", severity="low"),
            Finding(id="3", severity="high"),
        ]
        highs = store.get_findings_by_severity("high")
        assert len(highs) == 2


class TestPolicyReference:
    """公司规范引用测试"""

    @pytest.mark.asyncio
    async def test_add_policy_reference(self):
        """添加公司规范引用"""
        store = EvidenceStore()
        ref = PolicyReference(
            policy_id="POL-001",
            policy_area="sql_injection",
            policy_label="SQL 注入风险",
            rule_text="所有数据库查询必须使用参数化语句",
            matched_finding_ids=["SEC-001"],
        )
        await store.add_policy_reference(ref)
        assert len(store.policy_references) == 1

    @pytest.mark.asyncio
    async def test_get_policy_references_for_finding(self):
        """获取 finding 关联的政策引用"""
        store = EvidenceStore()
        await store.add_policy_reference(PolicyReference(
            policy_id="POL-001", matched_finding_ids=["SEC-001", "SEC-002"],
        ))
        await store.add_policy_reference(PolicyReference(
            policy_id="POL-002", matched_finding_ids=["SEC-003"],
        ))
        refs = store.get_policy_references_for_finding("SEC-001")
        assert len(refs) == 1
        assert refs[0].policy_id == "POL-001"


class TestChallengeAndDecision:
    """质疑和裁决记录测试"""

    @pytest.mark.asyncio
    async def test_add_challenge(self):
        """添加质疑记录（自动生成 ID）"""
        store = EvidenceStore()
        await store.add_challenge(Challenge(
            finding_id="SEC-001", challenger="Critic",
            action="CHALLENGE", reason="证据不足",
        ))
        assert len(store.challenges) == 1
        assert store.challenges[0].challenge_id == "CH-001"

    @pytest.mark.asyncio
    async def test_add_decision(self):
        """添加裁决记录（自动生成 ID）"""
        store = EvidenceStore()
        await store.add_decision(Decision(
            finding_id="SEC-001", action="ACCEPT", reason="证据充分",
        ))
        assert len(store.decisions) == 1
        assert store.decisions[0].decision_id == "DC-001"

    @pytest.mark.asyncio
    async def test_add_debate_round(self):
        """添加辩论轮次记录"""
        store = EvidenceStore()
        await store.add_debate_round(DebateRound(
            round_number=1, lead_action="CHALLENGE",
            target_finding_id="SEC-001", actor="Critic",
            result_summary="质疑成功", consensus_score=0.4,
            findings_count=5,
        ))
        assert len(store.debate_history) == 1
        assert store.consensus_score == 0.4


class TestPersistence:
    """持久化测试"""

    @pytest.mark.asyncio
    async def test_save_and_load_json(self):
        """保存并加载 EvidenceStore"""
        store = EvidenceStore(task_id="persist-test")
        await store.add_finding(Finding(
            id="SEC-001", category="security", severity="high",
            title="SQL注入", evidence="SELECT * FROM users WHERE id=" + "x",
        ))
        await store.add_policy_reference(PolicyReference(
            policy_id="POL-001", policy_area="sql_injection",
            rule_text="必须使用参数化查询",
        ))
        await store.add_decision(Decision(
            finding_id="SEC-001", action="ACCEPT", reason="证据充分",
        ))

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "evidence_store.json")
            store.save_json(path)

            # 验证文件存在且可读
            assert Path(path).exists()
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            assert data["task_id"] == "persist-test"
            assert len(data["findings"]) == 1

            # 加载并验证数据完整
            loaded = EvidenceStore.load_json(path)
            assert loaded.task_id == "persist-test"
            assert loaded.finding_count == 1
            assert loaded.get_finding("SEC-001").title == "SQL注入"
            assert len(loaded.policy_references) == 1
            assert loaded.policy_references[0].policy_id == "POL-001"
            assert len(loaded.decisions) == 1

    def test_to_dict_summary(self):
        """to_dict 包含正确的统计摘要"""
        store = EvidenceStore()
        store.findings = [
            Finding(id="1", severity="high"),
            Finding(id="2", severity="high"),
            Finding(id="3", severity="low"),
        ]
        d = store.to_dict()
        assert d["summary"]["total_findings"] == 3
        assert d["summary"]["severity_counts"]["high"] == 2
        assert d["summary"]["severity_counts"]["low"] == 1
