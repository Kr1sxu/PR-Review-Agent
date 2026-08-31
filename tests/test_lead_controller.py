"""
Lead Controller 单元测试 - PR-Review Agent v2
测试输出解析、裁决验证、动作验证
"""

import pytest
from src.agents.lead_controller import (
    create_lead_controller_agent,
    parse_lead_controller_output,
    validate_council_decision,
    validate_debate_action,
)
from agentscope.agent._agent import Agent
from src.models.mimo_wrapper import create_mimo_model


@pytest.fixture
def offline_model():
    """创建离线模型用于测试"""
    return create_mimo_model(api_url="", api_key="")


class TestLeadControllerCreation:
    """Lead Controller 创建测试"""

    def test_create_agent(self, offline_model):
        """创建 Lead Controller Agent"""
        agent = create_lead_controller_agent(offline_model)
        assert isinstance(agent, Agent)
        assert agent.name == "lead_controller"


class TestOutputParsing:
    """输出解析测试"""

    def test_parse_valid_council_output(self):
        """解析合法的 Council 模式输出"""
        text = '''
        ```json
        {
            "mode": "council",
            "decisions": [
                {"finding_id": "SEC-001", "action": "ACCEPT", "reason": "证据充分"},
                {"finding_id": "QUA-003", "action": "REJECT", "reason": "误报"}
            ],
            "consensus_score": 0.85,
            "summary": "裁决完成"
        }
        ```
        '''
        result = parse_lead_controller_output(text)
        assert result["mode"] == "council"
        assert len(result["decisions"]) == 2
        assert result["consensus_score"] == 0.85

    def test_parse_valid_debate_output(self):
        """解析合法的 Debate 模式输出"""
        text = '{"mode":"debate","action":"CHALLENGE","target_finding_id":"SEC-001","consensus_score":0.4}'
        result = parse_lead_controller_output(text)
        assert result["action"] == "CHALLENGE"
        assert result["target_finding_id"] == "SEC-001"

    def test_parse_invalid_output_returns_fallback(self):
        """解析失败时返回兜底结构"""
        text = "这不是 JSON 输出"
        result = parse_lead_controller_output(text)
        assert result["action"] == "ERROR"
        assert "raw" in result


class TestCouncilDecisionValidation:
    """Council 裁决验证测试"""

    def test_valid_accept(self):
        """合法的 ACCEPT 裁决"""
        assert validate_council_decision({"finding_id": "SEC-001", "action": "ACCEPT"}) is True

    def test_valid_reject(self):
        """合法的 REJECT 裁决"""
        assert validate_council_decision({"finding_id": "SEC-001", "action": "REJECT"}) is True

    def test_valid_downgrade(self):
        """合法的 DOWNGRADE 裁决"""
        d = {"finding_id": "SEC-001", "action": "DOWNGRADE", "new_severity": "low"}
        assert validate_council_decision(d) is True

    def test_downgrade_without_severity_invalid(self):
        """DOWNGRADE 缺少 new_severity 应无效"""
        d = {"finding_id": "SEC-001", "action": "DOWNGRADE"}
        assert validate_council_decision(d) is False

    def test_missing_finding_id_invalid(self):
        """缺少 finding_id 应无效"""
        assert validate_council_decision({"action": "ACCEPT"}) is False

    def test_invalid_action(self):
        """非法 action 应无效"""
        assert validate_council_decision({"finding_id": "SEC-001", "action": "INVALID"}) is False


class TestDebateActionValidation:
    """Debate 动作验证测试"""

    def test_valid_challenge(self):
        """合法的 CHALLENGE 动作"""
        d = {"action": "CHALLENGE", "target_finding_id": "SEC-001"}
        assert validate_debate_action(d) is True

    def test_valid_finish(self):
        """合法的 FINISH 动作（不需要 target）"""
        d = {"action": "FINISH", "consensus_score": 0.9}
        assert validate_debate_action(d) is True

    def test_challenge_without_target_invalid(self):
        """CHALLENGE 缺少 target 应无效"""
        d = {"action": "CHALLENGE"}
        assert validate_debate_action(d) is False

    def test_invalid_action_name(self):
        """非法动作名应无效"""
        d = {"action": "INVALID", "target_finding_id": "SEC-001"}
        assert validate_debate_action(d) is False
