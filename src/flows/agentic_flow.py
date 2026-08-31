"""
Agentic Flow - PR-Review Agent v2
扩展 Debate 流程，预留自主特性扩展点。
当前继承新版 DebateFlow，使用更大的 max_rounds。
"""

import logging
from typing import Dict

from src.flows.debate_flow import DebateFlow
from src.flows.base_flow import ReviewResult

logger = logging.getLogger(__name__)


class AgenticFlow(DebateFlow):
    """
    Agentic 自主流程（v2 继承新版 DebateFlow）。
    当前使用扩展配置（更多辩论轮次），未来可添加：
    - 自主工具使用和迭代细化
    - 自主证据收集
    - 自适应审查策略
    """

    @property
    def flow_mode(self) -> str:
        return "agentic"

    async def run(self, diff: str, pr_description: str, config: Dict) -> ReviewResult:
        self._logger.info("Agentic flow: using v2 debate pipeline with extended config")
        # 使用更大的 max_rounds，允许更深入的审查
        config.setdefault("max_rounds", 5)
        return await super().run(diff, pr_description, config)
