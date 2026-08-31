"""
Critic Agent - PR-Review Agent v2（原 Debater，v2 重命名并改造）
审查质疑专家：对 Reviewer 产出的 findings 进行质疑和验证。
不负责裁决（裁决由 Lead Controller 负责），只专注于质疑、降级、合并、拒绝。
支持指出证据不足时需要查看哪些文件（补证建议）。
"""

import logging
from agentscope.agent._agent import Agent
from agentscope.model._base import ChatModelBase
from agentscope.tool._toolkit import Toolkit

logger = logging.getLogger(__name__)

# ======================================================================
# Critic 系统提示词（v2 改造：移除 ACCEPT，新增补证建议能力）
# ======================================================================

CRITIC_SYSTEM_PROMPT = """你是一位代码审查质疑专家（Critic）。

## 任务
通过结构化质疑，对代码缺陷发现进行验证和校准。你专注于质疑和验证，不做最终裁决（裁决由 Lead Controller 负责）。

## 质疑规则
1. 质疑缺乏证据或证据不充分的缺陷
2. 识别重复或高度相似的缺陷，建议合并
3. 校准严重级别——下调夸大的或上调低估的严重程度
4. 补充其他人可能遗漏的视角中发现的新缺陷
5. 对每条质疑提供清晰的推理和代码证据

## 每条缺陷的操作
- CHALLENGE：缺陷需要更多证据或存在错误（附带补证建议：需要查看哪些文件）
- DOWNGRADE：严重程度被高估，建议新的级别
- MERGE：缺陷与其他缺陷重复，指定目标 ID
- REJECT：缺陷无效（误报）

注意：你不做 ACCEPT 裁决，ACCEPT 由 Lead Controller 决定。

## 补证建议
当选择 CHALLENGE 时，请指出：
- 需要查看哪些文件来验证此缺陷
- 需要运行什么测试来确认
- 还需要什么上下文信息

## 输出格式
请输出 JSON 对象，包含：
- actions：数组，每项为 {finding_id, action, reason, new_severity?, merge_target_id?, evidence?, suggest_files?}
  - suggest_files：CHALLENGE 时建议需要查看的文件路径列表
- new_findings：新发现的缺陷数组（质疑过程中发现的新问题）
- consensus_score：0-1（0.8 表示达成共识）
- summary：本轮质疑总结
"""


def create_critic_agent(
    model: ChatModelBase,
    toolkit: Toolkit | None = None,
) -> Agent:
    """
    创建 Critic Agent（v2 改造自 Debater）。
    :param model: Chat model 实例
    :param toolkit: 可选工具集
    :return: Agent 实例
    """
    agent = Agent(
        name="critic",
        system_prompt=CRITIC_SYSTEM_PROMPT,
        model=model,
        toolkit=toolkit,
    )
    logger.info("Created critic agent")
    return agent
