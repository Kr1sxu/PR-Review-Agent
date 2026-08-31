"""
Agents 单元测试 - PR-Review Agent v2
测试 Agent 创建、离线模式、工厂类
v2 变更：Scanner→Reviewer、Debater→Critic、删除 Merger、新增 Lead Controller + ReportWriterAgent
v2.1 变更：company_policy_reviewer 独立为文件，scanner_agent.py → reviewer_agent.py，删除 debater_agent.py
"""

import pytest
from agentscope.agent._agent import Agent

from src.models.mimo_wrapper import create_mimo_model
from src.agents.reviewer_agent import (
    create_reviewer_agent, REVIEWER_ROLES, SCANNER_ROLES,
)
from src.agents.company_policy_reviewer import create_company_policy_reviewer
from src.agents.critic_agent import create_critic_agent
from src.agents.lead_controller import create_lead_controller_agent
from src.agents.report_writer import create_report_writer_agent
from src.agents.judger_agent import create_judge_agent
from src.agents.agent_factory import AgentFactory
from src.tools.tool_registry import create_toolkit


@pytest.fixture
def offline_model():
    """创建离线 MiMo 模型用于测试"""
    return create_mimo_model(api_url="", api_key="")


@pytest.fixture
def toolkit():
    """创建默认工具集"""
    return create_toolkit()


class TestReviewerAgents:
    """v2 Reviewer Agent 测试（原 Scanner，5 个角色）"""

    def test_create_single_reviewer(self, offline_model, toolkit):
        """创建单个 Reviewer"""
        agent = create_reviewer_agent("security_expert", offline_model, toolkit)
        assert isinstance(agent, Agent)
        assert agent.name == "reviewer_security_expert"

    def test_create_all_reviewer_roles(self, offline_model, toolkit):
        """创建所有 5 个 Reviewer 角色"""
        for role in REVIEWER_ROLES:
            agent = create_reviewer_agent(role, offline_model, toolkit)
            assert isinstance(agent, Agent)
            assert agent.name == f"reviewer_{role}"

    def test_reviewer_roles_count(self):
        """应有 5 个 Reviewer 角色（不含 company_policy_reviewer）"""
        assert len(REVIEWER_ROLES) == 5
        assert "company_policy_reviewer" not in REVIEWER_ROLES

    def test_scanner_roles_backward_compat(self):
        """SCANNER_ROLES 应与 REVIEWER_ROLES 一致（向后兼容）"""
        assert SCANNER_ROLES is REVIEWER_ROLES

    def test_invalid_role_raises(self, offline_model):
        """无效角色名应抛出异常"""
        with pytest.raises(ValueError, match="Unknown reviewer role"):
            create_reviewer_agent("nonexistent_role", offline_model)

    def test_rag_context_injected(self, offline_model):
        """RAG 上下文应注入到 prompt 中"""
        rag = "Always check for SQL injection in payment code."
        agent = create_reviewer_agent("security_expert", offline_model, rag_context=rag)
        assert "SQL injection" in agent._system_prompt


class TestCompanyPolicyReviewer:
    """v2 独立的 company_policy_reviewer 测试（独立文件）"""

    def test_create_company_policy_reviewer(self, offline_model, toolkit):
        """创建 company_policy_reviewer"""
        agent = create_company_policy_reviewer(offline_model, toolkit)
        assert isinstance(agent, Agent)
        assert agent.name == "company_policy_reviewer"


class TestCriticAgent:
    """v2 Critic Agent 测试（原 Debater）"""

    def test_create_critic(self, offline_model, toolkit):
        """创建 Critic Agent"""
        agent = create_critic_agent(offline_model, toolkit)
        assert isinstance(agent, Agent)
        assert agent.name == "critic"

    def test_critic_prompt_contains_challenge(self, offline_model):
        """Critic prompt 应包含质疑动作"""
        agent = create_critic_agent(offline_model)
        assert "CHALLENGE" in agent._system_prompt
        assert "REJECT" in agent._system_prompt


class TestLeadControllerAgent:
    """v2 Lead Controller Agent 测试"""

    def test_create_lead_controller(self, offline_model, toolkit):
        """创建 Lead Controller"""
        agent = create_lead_controller_agent(offline_model, toolkit)
        assert isinstance(agent, Agent)
        assert agent.name == "lead_controller"

    def test_lead_prompt_contains_council_and_debate(self, offline_model):
        """Lead Controller prompt 应包含 Council 和 Debate 模式说明"""
        agent = create_lead_controller_agent(offline_model)
        assert "Council" in agent._system_prompt
        assert "Debate" in agent._system_prompt


class TestReportWriterAgent:
    """v2 ReportWriterAgent 测试"""

    def test_create_report_writer(self, offline_model):
        """创建 ReportWriterAgent"""
        agent = create_report_writer_agent(offline_model)
        assert isinstance(agent, Agent)
        assert agent.name == "report_writer"


class TestAgentFactoryV2:
    """v2 AgentFactory 测试"""

    def test_factory_create_all(self, offline_model):
        """create_all 应返回 v2 角色结构"""
        factory = AgentFactory(model=offline_model)
        agents = factory.create_all()
        assert "reviewers" in agents
        assert "company_policy_reviewer" in agents
        assert "critic" in agents
        assert "lead_controller" in agents
        assert "report_writer" in agents
        assert "judge" in agents
        # v2 不应有 merger / debater / scanners
        assert "merger" not in agents
        assert "debater" not in agents

    def test_factory_create_reviewers(self, offline_model):
        """工厂创建 Reviewer 组"""
        factory = AgentFactory(model=offline_model)
        reviewers = factory.create_reviewers()
        assert len(reviewers) == 5

    def test_factory_create_scanners_backward_compat(self, offline_model):
        """create_scanners 向后兼容别名"""
        factory = AgentFactory(model=offline_model)
        scanners = factory.create_scanners()
        assert len(scanners) == 5

    def test_factory_create_critic(self, offline_model):
        """工厂创建 Critic"""
        factory = AgentFactory(model=offline_model)
        critic = factory.create_critic()
        assert critic.name == "critic"

    def test_factory_create_lead_controller(self, offline_model):
        """工厂创建 Lead Controller"""
        factory = AgentFactory(model=offline_model)
        lead = factory.create_lead_controller()
        assert lead.name == "lead_controller"

    def test_factory_create_report_writer(self, offline_model):
        """工厂创建 ReportWriterAgent"""
        factory = AgentFactory(model=offline_model)
        writer = factory.create_report_writer()
        assert writer.name == "report_writer"
