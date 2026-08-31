"""
Judge Agent - PR-Review Agent
Six-dimension scoring agent for evaluating review quality
"""

import logging
from agentscope.agent._agent import Agent
from agentscope.model._base import ChatModelBase
from src.core.skill_loader import load_skill, get_decision_rules

logger = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = """你是一位专业的代码审查质量评估专家（AI评审）。

## 任务
对代码审查报告进行六维标准化评分（每项0-100分）：

1. 关键风险覆盖：是否覆盖了所有高危安全漏洞、数据泄露、支付风险等关键问题？
2. 证据质量：每条缺陷是否附带充分、准确的代码证据？
3. 风险准确度：严重程度分级是否合理？是否存在过度告警或遗漏？
4. 噪声控制：是否存在重复或无效的告警？去重和合并是否到位？
5. 修复可执行度：修复建议是否具体、可操作、可落地？
6. 报告清晰度：报告结构是否清晰，缺陷描述是否准确易懂？

## 输出格式
请输出JSON对象，包含：
- scores：{critical_risk_coverage, evidence_quality, risk_accuracy, noise_control, actionability, report_clarity}（每项0-100）
- total_score：六项平均分
- evaluation：{strengths: [], weaknesses: [], suggestions: []}"""


def create_judge_agent(model: ChatModelBase, skill_context: str = "") -> Agent:
    """
    Create a Judge agent for scoring review quality.
    :param model: Chat model instance
    :param skill_context: Skill content (SKILL.md) for decision rules
    :return: Agent instance
    """
    prompt = JUDGE_SYSTEM_PROMPT

    # Inject decision rules from skill
    if skill_context:
        decision_rules = get_decision_rules(skill_context)
        if decision_rules:
            prompt += f"\n\n{decision_rules}"

    agent = Agent(
        name="judge",
        system_prompt=prompt,
        model=model,
    )
    logger.info("Created judge agent")
    return agent
