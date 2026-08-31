"""
Reviewer Agent - PR-Review Agent v2
多角色代码审查 Agent，用于识别代码缺陷。
Reviewer 角色（5 个）：security_expert, logic_reviewer, test_engineer,
                      maintainability_reviewer, compliance_checker

注：company_policy_reviewer 已独立为 company_policy_reviewer.py，支持工具调用。
Reviewer 本身不使用工具，仅基于 diff 和 RAG 上下文进行分析。
跨文件调查由 company_policy_reviewer 负责。
"""

import logging
from typing import Optional

from agentscope.agent._agent import Agent
from agentscope.model._base import ChatModelBase
from agentscope.tool._toolkit import Toolkit
from src.core.skill_loader import load_skill, get_review_checklist, get_output_schema, get_anti_patterns

logger = logging.getLogger(__name__)

# ======================================================================
# Reviewer 角色定义（5 个）
# ======================================================================

REVIEWER_ROLES = {
    "security_expert": {
        "name": "安全专家",
        "prompt": (
            "你是一位资深安全专家，专注于代码安全审查。\n"
            "你的任务是识别安全漏洞，包括：\n"
            "SQL注入、XSS、CSRF、路径遍历、敏感数据泄露。\n"
            "硬编码密码、不安全的反序列化、认证绕过。\n"
            "授权缺陷和加密弱点。\n\n"
            "注意：如果 diff 中引用了其他文件的函数（如 `from xxx import yyy`），\n"
            "请基于函数名和上下文推断其行为。如果无法确定，\n"
            "在发现中标注「需进一步验证 xxx 函数的实现」并将 confidence 降低。\n\n"
            "对于每个发现，请提供：id、category、severity、title、description、\n"
            "file_path、line_range、evidence（代码片段）、suggestion、confidence（0-1）。"
        ),
    },
    "logic_reviewer": {
        "name": "逻辑审查员",
        "prompt": (
            "你是一位资深软件工程师，专注于业务逻辑审查。\n"
            "你的任务是识别逻辑错误，包括：\n"
            "空指针风险、边界条件错误、竞态条件。\n"
            "错误处理缺失、资源泄漏、算法逻辑错误。\n"
            "边界情况失败和状态管理问题。\n\n"
            "对于每个发现，请提供：id、category、severity、title、description、\n"
            "file_path、line_range、evidence、suggestion、confidence（0-1）。"
        ),
    },
    "test_engineer": {
        "name": "测试工程师",
        "prompt": (
            "你是一位QA工程师，专注于测试质量审查。\n"
            "你的任务是评估测试覆盖率和质量：\n"
            "缺失的测试用例、断言薄弱、测试隔离问题。\n"
            "缺少边界测试、测试反模式、覆盖空白。\n\n"
            "对于每个发现，请提供：id、category、severity、title、description、\n"
            "file_path、line_range、evidence、suggestion、confidence（0-1）。"
        ),
    },
    "maintainability_reviewer": {
        "name": "可维护性检查员",
        "prompt": (
            "你是一位软件架构师，专注于代码质量和可维护性。\n"
            "你的任务是识别可维护性问题：\n"
            "代码重复、复杂度过高、命名不规范。\n"
            "缺少文档、耦合过紧、上帝类/函数。\n"
            "违反SOLID原则和技术债务。\n\n"
            "对于每个发现，请提供：id、category、severity、title、description、\n"
            "file_path、line_range、evidence、suggestion、confidence（0-1）。"
        ),
    },
    "compliance_checker": {
        "name": "规范检查员",
        "prompt": (
            "你是一位合规专家，负责对照企业规范检查代码。\n"
            "你的任务是验证以下方面的合规性：\n"
            "编码规范、命名约定、文档要求。\n"
            "API设计准则、日志标准、错误处理模式\n"
            "和组织最佳实践。\n"
            "在可用时引用提供的知识库规范。\n\n"
            "对于每个发现，请提供：id、category、severity、title、description、\n"
            "file_path、line_range、evidence、suggestion、confidence（0-1）。\n"
            "spec_reference（如适用）。"
        ),
    },
}

SCANNER_ROLES = REVIEWER_ROLES


def create_reviewer_agent(
    role: str,
    model: ChatModelBase,
    toolkit: Toolkit | None = None,
    rag_context: str = "",
    skill_context: str = "",
) -> Agent:
    """
    创建 Reviewer Agent（5 个角色之一）。
    Reviewer 不使用工具，仅基于 diff 进行分析。
    跨文件调查由 company_policy_reviewer 负责。

    :param role: 角色键
    :param model: Chat model 实例
    :param toolkit: 不使用，传 None
    :param rag_context: RAG 知识库上下文
    :param skill_context: Skill 内容
    :return: Agent 实例
    """
    if role not in REVIEWER_ROLES:
        raise ValueError(f"Unknown reviewer role: {role}. Available: {list(REVIEWER_ROLES.keys())}")

    role_info = REVIEWER_ROLES[role]
    system_prompt = role_info["prompt"]

    if skill_context:
        checklist = get_review_checklist(skill_context)
        anti_patterns = get_anti_patterns(skill_context)
        if checklist:
            system_prompt += f"\n\n{checklist}"
        if anti_patterns:
            system_prompt += f"\n\n{anti_patterns}"

    if rag_context:
        system_prompt += f"\n\n## 相关企业规范\n{rag_context}"

    output_schema = get_output_schema(skill_context) if skill_context else ""
    if output_schema:
        system_prompt += f"\n\n{output_schema}"
    else:
        system_prompt += (
            "\n\n## 输出格式\n"
            "以JSON数组格式输出发现结果。每个发现必须包含：\n"
            "id、category、severity、title、description、file_path、line_range、\n"
            "evidence、suggestion、confidence。\n"
            "如果没有发现问题，输出：[]"
        )

    # Reviewer 不使用工具
    agent = Agent(
        name=f"reviewer_{role}",
        system_prompt=system_prompt,
        model=model,
        toolkit=None,
    )
    logger.info(f"Created reviewer agent: {role_info['name']}")
    return agent


create_scanner_agent = create_reviewer_agent
