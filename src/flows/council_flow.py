"""
Council Flow - PR-Review Agent v2
新版 Council 审查流程（原地替换 v1）。
流程：Reviewer x5 并行 → company_policy_reviewer → 合并 findings
      → Lead Controller 裁决 → Critic 质疑 → Lead Controller 最终确认
      → 写入 EvidenceStore

所有数据通过 EvidenceStore 流转，不再使用 Merger Agent。
"""

import asyncio
import json
import logging
import time
from typing import Dict, List

from agentscope.agent._agent import Agent
from agentscope.message._base import Msg

from src.flows.base_flow import BaseFlow, Finding, ReviewResult, finding_to_dict
from src.flows.evidence_store import EvidenceStore, PolicyReference
from src.agents.agent_factory import AgentFactory
from src.agents.lead_controller import parse_lead_controller_output, validate_council_decision
from src.agents.report_writer import generate_report, fallback_render
from src.models.schemas import FindingsOutput

logger = logging.getLogger(__name__)

# 单条 Agent 输出的最大长度（防止 token 溢出）
MAX_SCANNER_OUTPUT = 3000


class CouncilFlow(BaseFlow):
    """
    v2 Council 审查流程。
    Pipeline: Reviewer x5 并行 → company_policy_reviewer → 程序化合并
              → Lead Controller 裁决 → Critic 质疑 → Lead Controller 最终确认
              → EvidenceStore 持久化 → ReportWriterAgent 输出报告
    """

    def __init__(self, agent_factory: AgentFactory, **kwargs):
        super().__init__(**kwargs)
        self.factory = agent_factory

    @property
    def flow_mode(self) -> str:
        return "council"

    async def run(self, diff: str, pr_description: str, config: Dict) -> ReviewResult:
        rag_context = config.get("rag_context", "")
        roles = config.get("scanner_roles", None)
        task_id = config.get("task_id", "")

        # 初始化 EvidenceStore（所有数据的中枢）
        store = EvidenceStore(task_id=task_id)

        # ------------------------------------------------------------------
        # 步骤 1：Reviewer x5 并行审查
        # ------------------------------------------------------------------
        scanners = self.factory.create_scanners(roles=roles, rag_context=rag_context)
        self._logger.info(f"Council: running {len(scanners)} reviewers in parallel")
        scanner_results = await self._run_agents_parallel(
            scanners, diff, pr_description, step_name="reviewer"
        )

        # 解析各 Reviewer 的输出为 Finding 对象
        all_findings: List[Finding] = []
        for i, (role, output) in enumerate(zip(scanners.keys(), scanner_results)):
            parsed = self._parse_findings(output)
            # 为每条 finding 添加来源标识
            for f in parsed:
                f.id = f"R{i+1}-{f.id}" if not f.id.startswith("R") else f.id
                f.sources = f.sources or [role]
            all_findings.extend(parsed)

        # ------------------------------------------------------------------
        # 步骤 2：company_policy_reviewer 独立审查
        # ------------------------------------------------------------------
        policy_reviewer = self.factory.create_company_policy_reviewer(rag_context=rag_context)
        policy_result = await self._run_single_agent(
            policy_reviewer, diff, pr_description, step_name="company_policy_reviewer"
        )
        policy_findings = self._parse_findings(policy_result)
        for f in policy_findings:
            f.id = f"POL-{f.id}" if not f.id.startswith("POL") else f.id
            f.sources = f.sources or ["company_policy_reviewer"]
        all_findings.extend(policy_findings)

        # ------------------------------------------------------------------
        # 步骤 3：程序化去重合并（替代原 Merger Agent）
        # ------------------------------------------------------------------
        merged_findings = self._programmatic_merge(all_findings)
        self._logger.info(f"Council: {len(all_findings)} raw → {len(merged_findings)} merged findings")

        # 写入 EvidenceStore
        await store.add_findings(merged_findings)

        # ------------------------------------------------------------------
        # 步骤 4：Lead Controller 裁决
        # ------------------------------------------------------------------
        lead = self.factory.create_lead_controller()
        lead_result = await self._run_lead_council(lead, store, diff, pr_description)

        # 解析裁决结果并应用到 EvidenceStore
        decisions = lead_result.get("decisions", [])
        for d in decisions:
            if validate_c_decision(d):
                await self._apply_council_decision(store, d)

        # ------------------------------------------------------------------
        # 步骤 5：Critic 质疑（一轮）
        # ------------------------------------------------------------------
        if store.finding_count > 0:
            critic = self.factory.create_critic()
            await self._run_critic_challenge(critic, store, diff)

            # Lead Controller 最终确认（基于 Critic 质疑后的新状态）
            if store.finding_count > 0:
                lead_final = self.factory.create_lead_controller()
                final_result = await self._run_lead_council(
                    lead_final, store, diff, pr_description,
                    prompt_suffix="\n\n注意：Critic 已完成一轮质疑，请基于最新状态做最终确认。"
                )
                final_decisions = final_result.get("decisions", [])
                for d in final_decisions:
                    if validate_council_decision(d):
                        await self._apply_council_decision(store, d)

        # ------------------------------------------------------------------
        # 步骤 6：持久化 EvidenceStore
        # ------------------------------------------------------------------
        store_path = ""
        if task_id:
            import os
            store_path = os.path.join("output", "tasks", task_id, "evidence_store.json")
            store.save_json(store_path)
            self._logger.info(f"Council: EvidenceStore saved to {store_path}")

        # ------------------------------------------------------------------
        # 步骤 7：生成报告（优先 ReportWriterAgent，降级到模板渲染）
        # ------------------------------------------------------------------
        report_text = ""
        try:
            report_writer = self.factory.create_report_writer()
            report_text = await generate_report(
                report_writer, store.to_dict(),
                flow_mode="council", duration=0.0,
            )
        except Exception as e:
            self._logger.warning(f"ReportWriterAgent failed, falling back to template: {e}")

        if not report_text:
            report_text = fallback_render(store.to_dict(), flow_mode="council")

        # 保存报告到磁盘
        if task_id and report_text:
            import os
            report_path = os.path.join("output", "tasks", task_id, "report.md")
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report_text)

        # 构造返回结果
        summary = (
            f"Council 审查完成：{store.finding_count} 条发现，"
            f"{len(store.decisions)} 条裁决，{len(store.challenges)} 条质疑"
        )

        return ReviewResult(
            findings=list(store.findings),
            summary=summary,
            metadata={
                "scanner_count": len(scanners),
                "policy_reviewer": True,
                "lead_decisions": len(store.decisions),
                "critic_challenges": len(store.challenges),
                "evidence_store_path": store_path,
            },
        )

    # ==================================================================
    # Reviewer 并行执行
    # ==================================================================

    async def _run_agents_parallel(
        self,
        agents: Dict[str, Agent],
        diff: str,
        pr_description: str,
        step_name: str = "agent",
    ) -> List[str]:
        """并行运行多个 Agent，收集文本输出"""
        prompt = self._build_reviewer_prompt(diff, pr_description)

        async def run_one(role: str, agent: Agent) -> str:
            try:
                msg = Msg(name="user", role="user",
                          content=[{"type": "text", "text": prompt}])
                t0 = time.time()
                result = await agent.reply(msg)
                elapsed_ms = int((time.time() - t0) * 1000)

                output_text = "[]"
                if result and hasattr(result, 'content') and result.content:
                    texts = []
                    for block in result.content:
                        if hasattr(block, 'text') and block.text:
                            texts.append(block.text)
                    output_text = ''.join(texts) or "[]"

                self.transcript.log(
                    step=step_name, agent=role, action="call",
                    input_text=prompt, output_text=output_text,
                    duration_ms=elapsed_ms,
                )
                return output_text
            except Exception as e:
                logger.warning(f"Agent {role} failed: {e}")
                self.transcript.log(
                    step=step_name, agent=role, action="error",
                    input_text=prompt, output_text=str(e),
                )
                return "[]"

        tasks = [run_one(role, agent) for role, agent in agents.items()]
        results = await asyncio.gather(*tasks)
        return list(results)

    async def _run_single_agent(
        self,
        agent: Agent,
        diff: str,
        pr_description: str,
        step_name: str = "agent",
    ) -> str:
        """运行单个 Agent，返回文本输出。
        当 Agent 使用工具但超时未产出结构化输出时，
        从其上下文中提取最后一次有意义的推理输出。"""
        prompt = self._build_reviewer_prompt(diff, pr_description)
        try:
            msg = Msg(name="user", role="user",
                      content=[{"type": "text", "text": prompt}])
            t0 = time.time()
            result = await agent.reply(msg)
            elapsed_ms = int((time.time() - t0) * 1000)

            output_text = "[]"
            if result and hasattr(result, 'content') and result.content:
                texts = []
                for block in result.content:
                    if hasattr(block, 'text') and block.text:
                        texts.append(block.text)
                output_text = ''.join(texts) or "[]"

            # 如果输出是迭代超限消息，尝试从上下文提取最后一次有意义的输出
            if "maximum reasoning-acting iterations are exceeded" in output_text:
                fallback = self._extract_last_meaningful_output(agent)
                if fallback:
                    output_text = fallback
                    logger.info(f"Agent {agent.name}: extracted fallback output from context")

            self.transcript.log(
                step=step_name, agent=agent.name, action="call",
                input_text=prompt, output_text=output_text,
                duration_ms=elapsed_ms,
            )
            return output_text
        except Exception as e:
            logger.warning(f"Agent {agent.name} failed: {e}")
            self.transcript.log(
                step=step_name, agent=agent.name, action="error",
                input_text=prompt, output_text=str(e),
            )
            return "[]"

    @staticmethod
    def _extract_last_meaningful_output(agent: Agent) -> str:
        """从 Agent 上下文中提取最后一次包含 JSON 的文本输出。
        当工具调用循环导致迭代超限时，此方法可兜底提取中间推理结果。"""
        try:
            context = agent.state.context
            best = ""
            for msg in reversed(context):
                if not hasattr(msg, 'content'):
                    continue
                if isinstance(msg.content, list):
                    for block in msg.content:
                        if hasattr(block, 'text') and block.text:
                            text = block.text
                            # 跳过工具调用结果和系统消息
                            if 'maximum reasoning-acting' in text:
                                continue
                            if '"tool_result"' in text:
                                continue
                            # 寻找包含 JSON 的文本
                            if '[' in text and ']' in text and ('{' in text or 'id' in text):
                                return text
                            # 保留最后一个有实质内容的文本
                            if len(text) > 50 and '<tool_call>' not in text:
                                best = text
                elif isinstance(msg.content, str):
                    text = msg.content
                    if '[' in text and ']' in text and '{' in text:
                        return text
            return best
        except Exception:
            return ""

    # ==================================================================
    # Lead Controller 裁决（Council 模式）
    # ==================================================================

    async def _run_lead_council(
        self,
        lead: Agent,
        store: EvidenceStore,
        diff: str,
        pr_description: str,
        prompt_suffix: str = "",
    ) -> dict:
        """
        调用 Lead Controller 对 EvidenceStore 中的 findings 进行一次性裁决。
        返回解析后的裁决结果字典。
        """
        # 构造裁决 prompt：注入当前 findings + policy_references
        findings_json = json.dumps(
            [finding_to_dict(f) for f in store.findings],
            ensure_ascii=False, indent=2,
        )
        policy_refs_json = json.dumps(
            [r.to_dict() for r in store.policy_references],
            ensure_ascii=False, indent=2,
        )

        prompt = (
            f"## 当前审查发现（共 {store.finding_count} 条）\n"
            f"```json\n{findings_json}\n```\n\n"
            f"## 公司规范引用\n"
            f"```json\n{policy_refs_json}\n```\n\n"
            f"## 代码变更 (Diff)\n```\n{diff[:4000]}\n```\n\n"
            f"请以 Council 模式对每条 finding 做出裁决（ACCEPT/REJECT/DOWNGRADE/SUPPLEMENT）。"
            f"{prompt_suffix}"
        )

        try:
            msg = Msg(name="user", role="user",
                      content=[{"type": "text", "text": prompt}])
            t0 = time.time()
            result = await lead.reply(msg)
            elapsed_ms = int((time.time() - t0) * 1000)

            output_text = '{"mode":"council","decisions":[],"consensus_score":0.0}'
            if result and hasattr(result, 'content') and result.content:
                texts = []
                for block in result.content:
                    if hasattr(block, 'text') and block.text:
                        texts.append(block.text)
                output_text = ''.join(texts) or output_text

            self.transcript.log(
                step="lead_controller", agent="LeadController", action="council_decision",
                input_text=prompt, output_text=output_text,
                duration_ms=elapsed_ms,
                metadata={"findings_count": store.finding_count},
            )

            return parse_lead_controller_output(output_text)
        except Exception as e:
            logger.warning(f"Lead Controller council decision failed: {e}")
            return {"mode": "council", "decisions": [], "consensus_score": 0.0}

    # ==================================================================
    # 应用 Lead Controller 裁决到 EvidenceStore
    # ==================================================================

    async def _apply_council_decision(self, store: EvidenceStore, decision: dict) -> None:
        """将一条裁决应用到 EvidenceStore"""
        from src.flows.evidence_store import Decision

        finding_id = decision.get("finding_id", "")
        action = decision.get("action", "").upper()
        reason = decision.get("reason", "")
        new_severity = decision.get("new_severity", "")

        # 记录裁决
        await store.add_decision(Decision(
            finding_id=finding_id,
            action=action,
            reason=reason,
            new_severity=new_severity,
        ))

        # 执行裁决动作
        if action == "REJECT":
            await store.remove_finding(finding_id)
            logger.info(f"Lead REJECT: {finding_id}")
        elif action == "DOWNGRADE" and new_severity:
            finding = store.get_finding(finding_id)
            if finding:
                finding.severity = new_severity
                logger.info(f"Lead DOWNGRADE: {finding_id} -> {new_severity}")
        elif action == "ACCEPT":
            logger.debug(f"Lead ACCEPT: {finding_id}")
        elif action == "SUPPLEMENT":
            logger.debug(f"Lead SUPPLEMENT: {finding_id} (标记需补充调查)")

    # ==================================================================
    # Critic 质疑（一轮）
    # ==================================================================

    async def _run_critic_challenge(
        self,
        critic: Agent,
        store: EvidenceStore,
        diff: str,
    ) -> None:
        """调用 Critic 对 EvidenceStore 中的 findings 进行一轮质疑"""
        from src.flows.evidence_store import Challenge
        from src.flows.base_flow import apply_debate_actions

        findings_json = json.dumps(
            [finding_to_dict(f) for f in store.findings],
            ensure_ascii=False, indent=2,
        )

        prompt = (
            f"## 当前缺陷列表（共 {store.finding_count} 条）\n"
            f"```json\n{findings_json}\n```\n\n"
            f"## 代码变更 (Diff)\n```\n{diff[:4000]}\n```\n\n"
            f"请对这些缺陷进行质疑和验证。\n"
            f"输出包含 actions、new_findings、consensus_score 和 summary 的 JSON 对象。"
        )

        try:
            msg = Msg(name="user", role="user",
                      content=[{"type": "text", "text": prompt}])
            t0 = time.time()
            result = await critic.reply(msg)
            elapsed_ms = int((time.time() - t0) * 1000)

            output_text = '{"consensus_score": 0.0, "actions": []}'
            if result and hasattr(result, 'content') and result.content:
                texts = []
                for block in result.content:
                    if hasattr(block, 'text') and block.text:
                        texts.append(block.text)
                output_text = ''.join(texts) or output_text

            self.transcript.log(
                step="critic", agent="Critic", action="challenge",
                input_text=prompt, output_text=output_text,
                duration_ms=elapsed_ms,
                metadata={"findings_count": store.finding_count},
            )

            # 解析 Critic 输出
            parsed = self._extract_json(output_text)
            actions = parsed.get("actions", [])
            new_findings_raw = parsed.get("new_findings", [])
            consensus = parsed.get("consensus_score", 0.0)

            # 记录质疑到 EvidenceStore
            for a in actions:
                if isinstance(a, dict):
                    await store.add_challenge(Challenge(
                        finding_id=a.get("finding_id", ""),
                        challenger="Critic",
                        action=a.get("action", ""),
                        reason=a.get("reason", ""),
                        new_severity=a.get("new_severity", ""),
                        merge_target_id=a.get("merge_target_id", ""),
                    ))

            # 应用 Critic 的 actions 到 findings（使用现有工具函数）
            updated_findings = apply_debate_actions(
                list(store.findings), actions, new_findings_raw,
            )
            store.findings = updated_findings

            logger.info(
                f"Critic challenge: {len(actions)} actions, "
                f"consensus={consensus:.2f}, {store.finding_count} findings remain"
            )

        except Exception as e:
            logger.warning(f"Critic challenge failed: {e}")

    # ==================================================================
    # 程序化去重合并（替代原 Merger Agent）
    # ==================================================================

    @staticmethod
    def _programmatic_merge(findings: List[Finding]) -> List[Finding]:
        """
        程序化去重合并：按标题+文件路径+描述相似度去重。
        保留最高严重级别、合并证据和来源。
        """
        from difflib import SequenceMatcher

        def similarity(a: str, b: str) -> float:
            if not a or not b:
                return 0.0
            return SequenceMatcher(None, a.lower(), b.lower()).ratio()

        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        merged: List[Finding] = []
        used: set = set()

        for i, f1 in enumerate(findings):
            if i in used:
                continue
            best = Finding(**f1.__dict__)
            for j, f2 in enumerate(findings):
                if j <= i or j in used:
                    continue
                # 判断是否重复：同文件 + 标题相似，或标题+描述都相似
                same_file = f1.file_path == f2.file_path
                title_sim = similarity(f1.title, f2.title)
                desc_sim = similarity(f1.description[:100], f2.description[:100])
                is_dup = (same_file and title_sim > 0.6) or (title_sim > 0.7 and desc_sim > 0.5)
                if is_dup:
                    # 合并：保留更高严重级别、更长的证据
                    if sev_order.get(f2.severity, 9) < sev_order.get(best.severity, 9):
                        best.severity = f2.severity
                    if len(f2.evidence) > len(best.evidence):
                        best.evidence = f2.evidence
                    if len(f2.description) > len(best.description):
                        best.description = f2.description
                    best.confidence = max(best.confidence, f2.confidence)
                    best.sources = list(set(best.sources + f2.sources))
                    used.add(j)
            used.add(i)
            merged.append(best)

        # 按严重级别排序
        merged.sort(key=lambda f: sev_order.get(f.severity, 9))
        return merged

    # ==================================================================
    # 工具方法
    # ==================================================================

    @staticmethod
    def _build_reviewer_prompt(diff: str, pr_description: str) -> str:
        """构造 Reviewer / company_policy_reviewer 的统一审查 prompt"""
        return (
            f"请审查以下代码变更。\n\n"
            f"## PR 描述\n{pr_description}\n\n"
            f"## 代码变更 (Diff)\n```\n{diff}\n```\n\n"
            f"以 JSON 数组格式输出缺陷发现。"
        )

    @staticmethod
    def _parse_findings(text: str) -> List[Finding]:
        """从 Agent 输出文本中解析 Finding 对象列表"""
        findings = []
        try:
            from src.models.mimo_wrapper import MiMoChatModel
            parsed = MiMoChatModel.extract_json(text)
            if parsed is None:
                return []

            items = []
            if isinstance(parsed, dict):
                items = parsed.get("merged_findings", parsed.get("findings", []))
            elif isinstance(parsed, list):
                items = parsed

            for item in items:
                if isinstance(item, dict):
                    findings.append(Finding(
                        id=item.get("id", ""),
                        category=item.get("category", ""),
                        severity=item.get("severity", "medium"),
                        title=item.get("title", ""),
                        description=item.get("description", ""),
                        file_path=item.get("file_path", ""),
                        line_range=item.get("line_range", ""),
                        evidence=item.get("evidence", ""),
                        suggestion=item.get("suggestion", ""),
                        confidence=item.get("confidence", 0.5),
                        spec_reference=item.get("spec_reference", ""),
                        sources=item.get("sources", []),
                    ))
        except Exception as e:
            logger.warning(f"Failed to parse findings: {e}")
        return findings

    @staticmethod
    def _extract_json(text: str) -> dict:
        """从文本中提取 JSON 对象"""
        try:
            from src.models.mimo_wrapper import MiMoChatModel
            parsed = MiMoChatModel.extract_json(text)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}



