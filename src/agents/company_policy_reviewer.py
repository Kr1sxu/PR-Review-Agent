"""
Company Policy Reviewer Agent - PR-Review Agent v2
独立的公司策略审查智能体。

使用 read_file 工具主动读取 diff 中引用的外部文件，
结合公司规范发现潜在违规问题。

注意：MiMo 模型不支持 tool_choice，工具调用循环可能超时。
已设置 max_iters=5 作为防护。
"""

import logging

from agentscope.agent._agent import Agent
from agentscope.agent._config import ReActConfig
from agentscope.model._base import ChatModelBase
from agentscope.tool._toolkit import Toolkit
from src.core.skill_loader import get_review_checklist

logger = logging.getLogger(__name__)

# 低迭代次数防护 — MiMo 不支持 tool_choice，可能进入循环
_SAFE_REACT_CONFIG = ReActConfig(max_iters=5)

COMPANY_POLICY_REVIEWER_ROLE = {
    "name": "公司策略审查员",
    "prompt": (
        "你是一位资深合规工程师。你的任务是审查代码变更。\n\n"
        "## 工作流程\n"
        "1. 分析 diff，识别涉及的关键操作\n"
        "2. 如果 diff 中 `from xxx import yyy`，使用 `read_file` 读取 xxx 文件\n"
        "3. 结合读取结果，输出 JSON 数组格式的发现\n\n"
        "## 输出格式\n"
        "以 JSON 数组格式输出，每条包含：\n"
        "id, category, severity, title, description, file_path, line_range,\n"
        "evidence, suggestion, confidence, policy_reference\n"
        "如果没有发现违规，输出空数组 []"
    ),
}


def create_company_policy_reviewer(
    model: ChatModelBase,
    toolkit: Toolkit | None = None,
    rag_context: str = "",
    skill_context: str = "",
) -> Agent:
    system_prompt = COMPANY_POLICY_REVIEWER_ROLE["prompt"]

    if skill_context:
        checklist = get_review_checklist(skill_context)
        if checklist:
            system_prompt += f"\n\n{checklist}"

    if rag_context:
        system_prompt += f"\n\n## 相关企业规范\n{rag_context}"

    agent = Agent(
        name="company_policy_reviewer",
        system_prompt=system_prompt,
        model=model,
        toolkit=toolkit,
        react_config=_SAFE_REACT_CONFIG,
    )
    logger.info("Created company policy reviewer agent")
    return agent
