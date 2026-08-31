"""
Lead Controller Agent - PR-Review Agent v2
审查流程的总指挥：负责动态裁决和调度。
- Council 模式：对每条 finding 做 ACCEPT / REJECT / DOWNGRADE / SUPPLEMENT 裁决
- Debate 模式：每轮动态选择下一步 action，调度 Critic / Reviewer / 工具
"""

import json
import logging
from typing import Dict, List, Optional

from agentscope.agent._agent import Agent
from agentscope.model._base import ChatModelBase
from agentscope.tool._toolkit import Toolkit

logger = logging.getLogger(__name__)

# ======================================================================
# Lead Controller 系统提示词
# ======================================================================

LEAD_CONTROLLER_SYSTEM_PROMPT = """你是 PR 审查流程的总指挥（Lead Controller）。

## 职责
你负责对审查发现（Findings）进行最终裁决和动态调度。你需要基于证据质量、严重程度合理性、
公司规范合规性，做出客观、准确的判断。

## Council 模式（一次性裁决）
收到所有 Reviewer 和 company_policy_reviewer 的审查结果后，对每条 finding 做出裁决：

裁决动作：
- ACCEPT：finding 有效，证据充分，保留
- REJECT：finding 无效（误报），移除
- DOWNGRADE：严重程度被高估，调整为更合理的级别
- SUPPLEMENT：证据不足，但问题可能存在，标记需要补充调查

输出格式（Council 模式）：
```json
{
  "mode": "council",
  "decisions": [
    {"finding_id": "SEC-001", "action": "ACCEPT", "reason": "..."},
    {"finding_id": "QUA-003", "action": "REJECT", "reason": "..."},
    {"finding_id": "POL-002", "action": "DOWNGRADE", "new_severity": "low", "reason": "..."}
  ],
  "summary": "本轮裁决总结",
  "consensus_score": 0.85
}
```

## Debate 模式（多轮动态调度）
每一轮你需要分析当前 findings 状态，选择最合适的下一步动作：

调度动作：
- CHALLENGE：指派 Critic 对指定 finding 进行质疑验证
- REBUTTAL：指派 Reviewer 对 Critic 的质疑进行反驳
- SUPPLEMENT：指派工具补充证据（读取文件 / 搜索代码 / 运行测试）
- MERGE：合并两个相似 findings（直接操作）
- ACCEPT：接受该 finding（不再质疑）
- REJECT：拒绝该 finding（误报，移除）

输出格式（Debate 模式）：
```json
{
  "mode": "debate",
  "action": "CHALLENGE",
  "target_finding_id": "SEC-001",
  "reason": "需要验证此SQL注入是否在可达代码路径中",
  "assignee": "Critic",
  "consensus_score": 0.4,
  "summary": "当前进度描述"
}
```

当所有 findings 都已裁决完毕或达到足够共识时：
```json
{
  "mode": "debate",
  "action": "FINISH",
  "consensus_score": 0.9,
  "summary": "所有 findings 已审查完毕",
  "decisions": [...]
}
```

## 裁决原则
1. 证据优先：有明确代码证据的 finding 优先保留
2. 合规刚性：涉及公司规范（policy_references）的问题，除非明显误报，否则保留
3. 严重级别校准：P0/P1 仅限真正影响安全/资金的问题
4. 去重合并：描述高度相似的 findings 应合并而非保留多条
5. 误报清理：置信度低于 0.3 且无具体证据的 finding 应 REJECT
"""


def create_lead_controller_agent(
    model: ChatModelBase,
    toolkit: Toolkit | None = None,
) -> Agent:
    """
    创建 Lead Controller Agent。
    :param model: Chat model 实例
    :param toolkit: 可选工具集（Debate 模式下可能需要调用工具补证）
    :return: Agent 实例
    """
    agent = Agent(
        name="lead_controller",
        system_prompt=LEAD_CONTROLLER_SYSTEM_PROMPT,
        model=model,
        toolkit=toolkit,
    )
    logger.info("Created lead controller agent")
    return agent


# ======================================================================
# 输出解析工具函数
# ======================================================================

def parse_lead_controller_output(text: str) -> dict:
    """
    解析 Lead Controller 的模型输出为结构化字典。
    支持从纯文本中提取 JSON（处理 markdown code block 等情况）。
    解析失败时返回兜底结构，避免流程中断。
    :param text: 模型原始输出文本
    :return: 解析后的字典，解析失败返回 {"mode": "unknown", "action": "ERROR", "raw": text}
    """
    try:
        from src.models.mimo_wrapper import MiMoChatModel
        parsed = MiMoChatModel.extract_json(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception as e:
        logger.warning(f"Lead Controller output parse failed: {e}")

    # 解析失败，返回兜底结构
    return {"mode": "unknown", "action": "ERROR", "raw": text}


def validate_council_decision(decision: dict) -> bool:
    """验证 Council 模式下单条裁决的合法性（必须有 finding_id 和合法 action）"""
    if not decision.get("finding_id"):
        return False
    action = decision.get("action", "").upper()
    if action not in ("ACCEPT", "REJECT", "DOWNGRADE", "SUPPLEMENT"):
        return False
    # DOWNGRADE 必须指定新的严重级别
    if action == "DOWNGRADE" and not decision.get("new_severity"):
        return False
    return True


def validate_debate_action(parsed: dict) -> bool:
    """验证 Debate 模式下调度动作的合法性（必须有合法 action 和 target）"""
    action = parsed.get("action", "").upper()
    valid_actions = ("CHALLENGE", "REBUTTAL", "SUPPLEMENT", "MERGE", "ACCEPT", "REJECT", "FINISH")
    if action not in valid_actions:
        return False
    # FINISH 不需要 target，其余动作必须有 target_finding_id
    if action != "FINISH" and not parsed.get("target_finding_id"):
        return False
    return True
