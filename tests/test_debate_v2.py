"""
Debate v2 流程测试 - PR-Review Agent v2
测试 action 路由逻辑（不依赖真实模型）
"""

import pytest
from src.flows.debate_flow import DebateFlow
from src.flows.evidence_store import EvidenceStore, Decision
from src.flows.base_flow import Finding


class TestDebateFlowCreation:
    """DebateFlow 创建测试"""

    def test_flow_mode(self):
        """flow_mode 属性应返回 debate"""
        from src.models.mimo_wrapper import create_mimo_model
        from src.agents.agent_factory import AgentFactory
        model = create_mimo_model(api_url="", api_key="")
        factory = AgentFactory(model=model)
        flow = DebateFlow(agent_factory=factory, max_rounds=3)
        assert flow.flow_mode == "debate"


class TestActionRouting:
    """Action 路由逻辑测试（使用 EvidenceStore 操作验证）"""

    @pytest.mark.asyncio
    async def test_accept_action_records_decision(self):
        """ACCEPT 动应记录裁决"""
        store = EvidenceStore()
        await store.add_finding(Finding(id="SEC-001", title="测试"))
        await store.add_decision(Decision(
            finding_id="SEC-001", action="ACCEPT", reason="证据充分",
        ))
        assert len(store.decisions) == 1
        assert store.finding_count == 1  # ACCEPT 不移除 finding

    @pytest.mark.asyncio
    async def test_reject_action_removes_finding(self):
        """REJECT 动作应移除 finding"""
        store = EvidenceStore()
        await store.add_finding(Finding(id="SEC-001", title="误报"))
        await store.add_decision(Decision(
            finding_id="SEC-001", action="REJECT", reason="误报",
        ))
        await store.remove_finding("SEC-001")
        assert store.finding_count == 0

    @pytest.mark.asyncio
    async def test_merge_action(self):
        """MERGE 动作应合并 findings"""
        store = EvidenceStore()
        await store.add_finding(Finding(id="SEC-001", title="问题A", severity="medium"))
        await store.add_finding(Finding(id="SEC-002", title="问题A", severity="high"))
        success = await store.merge_findings("SEC-001", "SEC-002")
        assert success is True
        assert store.finding_count == 1

    @pytest.mark.asyncio
    async def test_debate_round_recording(self):
        """辩论轮次应正确记录到 EvidenceStore"""
        from src.flows.evidence_store import DebateRound
        store = EvidenceStore()
        await store.add_finding(Finding(id="SEC-001", title="测试"))
        await store.add_debate_round(DebateRound(
            round_number=1,
            lead_action="CHALLENGE",
            target_finding_id="SEC-001",
            actor="Critic",
            result_summary="质疑成功",
            consensus_score=0.4,
            findings_count=1,
        ))
        assert len(store.debate_history) == 1
        assert store.consensus_score == 0.4

    @pytest.mark.asyncio
    async def test_consensus_reached(self):
        """共识分数 >= 0.8 应视为达成共识"""
        from src.flows.evidence_store import DebateRound
        store = EvidenceStore()
        for i in range(3):
            await store.add_debate_round(DebateRound(
                round_number=i + 1,
                consensus_score=0.3 + i * 0.3,
                findings_count=5 - i,
            ))
        assert store.consensus_score >= 0.8  # 第3轮: 0.9
