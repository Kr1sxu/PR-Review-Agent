"""Agent Factory v2.2 - Tiered Model"""

import logging
from typing import Optional

from agentscope.agent._agent import Agent
from agentscope.model._base import ChatModelBase
from agentscope.tool._toolkit import Toolkit

from src.agents.reviewer_agent import create_reviewer_agent, REVIEWER_ROLES
from src.agents.company_policy_reviewer import create_company_policy_reviewer
from src.agents.critic_agent import create_critic_agent
from src.agents.lead_controller import create_lead_controller_agent
from src.agents.report_writer import create_report_writer_agent
from src.agents.judger_agent import create_judge_agent
from src.tools.tool_registry import create_toolkit
from src.core.skill_loader import load_skill

logger = logging.getLogger(__name__)


class AgentFactory:

    def __init__(self, model=None, strong_model=None, medium_model=None, light_model=None, embedding_model=None, toolkit=None, enable_tests=False, allowed_roots=None, skill_path=None, repo_path="."):
        self.strong_model = strong_model or model
        self.medium_model = medium_model or model or self.strong_model
        self.light_model = light_model or model or self.medium_model
        self.embedding_model = embedding_model
        self.model = self.strong_model

        if self.strong_model is None:
            raise ValueError("Need at least model or strong_model")

        self.toolkit = toolkit or create_toolkit(allowed_roots=allowed_roots, enable_tests=enable_tests, repo_path=repo_path)
        self.offline = getattr(self.strong_model, "offline", False)
        self.skill_context = load_skill(skill_path)

        logger.info(f"AgentFactory: strong={self.strong_model.__class__.__name__} medium={self.medium_model.__class__.__name__} light={self.light_model.__class__.__name__}")

    def create_reviewers(self, roles=None, rag_context=""):
        if roles is None: roles = list(REVIEWER_ROLES.keys())
        reviewers = {}
        for role in roles:
            reviewers[role] = create_reviewer_agent(role=role, model=self.light_model, toolkit=self.toolkit, rag_context=rag_context, skill_context=self.skill_context)
        return reviewers

    create_scanners = create_reviewers

    def create_company_policy_reviewer(self, rag_context=""):
        return create_company_policy_reviewer(model=self.medium_model, toolkit=self.toolkit, rag_context=rag_context, skill_context=self.skill_context)

    def create_critic(self):
        return create_critic_agent(model=self.strong_model, toolkit=self.toolkit)

    def create_lead_controller(self):
        return create_lead_controller_agent(model=self.strong_model, toolkit=self.toolkit)

    def create_report_writer(self):
        return create_report_writer_agent(model=self.strong_model)

    def create_judge(self):
        return create_judge_agent(model=self.strong_model, skill_context=self.skill_context)

    def create_all(self, rag_context="", skill_context=""):
        return {"reviewers": self.create_reviewers(rag_context=rag_context), "company_policy_reviewer": self.create_company_policy_reviewer(rag_context=rag_context), "critic": self.create_critic(), "lead_controller": self.create_lead_controller(), "report_writer": self.create_report_writer(), "judge": self.create_judge()}
