"""
Debate Flow - PR-Review Agent v2
新版 Debate 审查流程（原地替换 v1）。
流程：Reviewer x5 + company_policy_reviewer 并行 → 写入 EvidenceStore
      → 多轮 Lead Controller 动态调度（质疑/反驳/补证/合并/接收/拒绝）
      → EvidenceStore 持久化 → ReportWriterAgent 输出报告

核心区别：由 Lead Controller 主导调度，而非 Debater 自行输出 actions。
"""

import asyncio
import json
import logging
import time
from typing import Dict, List

from agentscope.agent._agent import Agent
from agentscope.message._base import Msg

from src.flows.council_flow import CouncilFlow
from src.flows.base_flow import Finding, ReviewResult, finding_to_dict, apply_debate_actions
from src.flows.evidence_store import EvidenceStore, Challenge, Decision, DebateRound
from src.agents.agent_factory import AgentFactory
from src.agents.lead_controller import parse_lead_controller_output, validate_debate_action
from src.agents.report_writer import generate_report, fallback_render

logger = logging.getLogger(__name__)


class DebateFlow(CouncilFlow):
    """
    v2 Debate 审查流程（继承 CouncilFlow 复用并行审查和工具方法）。
    Lead Controller 动态调度多轮博弈，替代原 Debater 驱动的 actions 模式。
    """

    def __init__(self, agent_factory: AgentFactory, max_rounds: int = 3, **kwargs):
        super().__init__(agent_factory=agent_factory, **kwargs)
        self.max_rounds = max_rounds

    @property
    def flow_mode(self) -> str:
        return "debate"

    async def run(self, diff: str, pr_description: str, config: Dict) -> ReviewResult:
        rag_context = config.get("rag_context", "")
        roles = config.get("scanner_roles", None)
        max_rounds = config.get("max_rounds", self.max_rounds)
        task_id = config.get("task_id", "")

        # 初始化 EvidenceStore
        store = EvidenceStore(task_id=task_id)

        # ==================================================================
        # 阶段 A：并行审查（复用 CouncilFlow 的审查逻辑）
        # ==================================================================

        # Reviewer x5 并行
        scanners = self.factory.create_scanners(roles=roles, rag_context=rag_context)
        self._logger.info(f"Debate: running {len(scanners)} reviewers in parallel")
        scanner_results = await self._run_agents_parallel(
            scanners, diff, pr_description, step_name="reviewer"
        )

        # 解析 Reviewer 输出为 Finding 对象
        all_findings: List[Finding] = []
        for i, (role, output) in enumerate(zip(scanners.keys(), scanner_results)):
            parsed = self._parse_findings(output)
            for f in parsed:
                f.id = f"R{i+1}-{f.id}" if not f.id.startswith("R") else f.id
                f.sources = f.sources or [role]
            all_findings.extend(parsed)

        # company_policy_reviewer 独立审查
        policy_reviewer = self.factory.create_company_policy_reviewer(rag_context=rag_context)
        policy_result = await self._run_single_agent(
            policy_reviewer, diff, pr_description, step_name="company_policy_reviewer"
        )
        policy_findings = self._parse_findings(policy_result)
        for f in policy_findings:
            f.id = f"POL-{f.id}" if not f.id.startswith("POL") else f.id
            f.sources = f.sources or ["company_policy_reviewer"]
        all_findings.extend(policy_findings)

        # 程序化去重合并
        merged_findings = self._programmatic_merge(all_findings)
        self._logger.info(f"Debate: {len(all_findings)} raw → {len(merged_findings)} merged")

        # 写入 EvidenceStore
        await store.add_findings(merged_findings)

        # 如果没有 findings，直接返回
        if store.is_empty:
            return ReviewResult(
                findings=[],
                summary="Debate 审查完成：未发现缺陷",
                metadata={"debate_rounds": 0, "consensus_score": 1.0},
            )

        # ==================================================================
        # 阶段 B：多轮 Lead Controller 动态调度
        # ==================================================================
        lead = self.factory.create_lead_controller()
        critic = self.factory.create_critic()
        consensus_score = 0.0

        for round_num in range(1, max_rounds + 1):
            self._logger.info(
                f"Debate round {round_num}/{max_rounds} "
                f"({store.finding_count} findings in play)"
            )

            # Lead Controller 选择下一步动作
            lead_output = await self._run_lead_debate_round(
                lead, store, diff, pr_description, round_num,
            )
            action = lead_output.get("action", "").upper()
            # 共识分：取模型自报和程序化计算的较大值
            model_score = lead_output.get("consensus_score", 0.0)
            program_score = self._compute_consensus_score(store)
            consensus_score = max(model_score, program_score)
            target_id = lead_output.get("target_finding_id", "")
            reason = lead_output.get("reason", "")

            # 记录本轮辩论到 EvidenceStore
            round_record = DebateRound(
                round_number=round_num,
                lead_action=action,
                target_finding_id=target_id,
                result_summary=lead_output.get("summary", ""),
                consensus_score=consensus_score,
                findings_count=store.finding_count,
            )

            # 终止条件：FINISH 动作或共识达成
            if action == "FINISH":
                if consensus_score < 0.5:
                    consensus_score = max(consensus_score, self._compute_consensus_score(store))
                self._logger.info(f"Debate: FINISH at round {round_num} (consensus={consensus_score:.2f})")
                round_record.actor = "LeadController"
                round_record.consensus_score = consensus_score
                await store.add_debate_round(round_record)
                # 应用 FINISH 时附带的 decisions
                for d in lead_output.get("decisions", []):
                    from src.agents.lead_controller import validate_council_decision
                    if validate_council_decision(d):
                        await self._apply_council_decision(store, d)
                break

            # 根据 action 路由到对应角色执行
            actor_result = await self._route_action(
                action, target_id, reason, lead_output,
                critic, store, diff, round_num,
            )
            round_record.actor = actor_result.get("actor", "unknown")
            round_record.result_summary = actor_result.get("summary", round_record.result_summary)
            await store.add_debate_round(round_record)

            # 共识达成
            if consensus_score >= 0.8:
                self._logger.info(f"Debate: consensus reached at round {round_num} ({consensus_score:.2f})")
                break

            # findings 已清空
            if store.is_empty:
                self._logger.info(f"Debate: all findings resolved at round {round_num}")
                break

        # ==================================================================
        # 阶段 C：持久化 EvidenceStore
        # ==================================================================
        store_path = ""
        if task_id:
            import os
            store_path = os.path.join("output", "tasks", task_id, "evidence_store.json")
            store.save_json(store_path)
            self._logger.info(f"Debate: EvidenceStore saved to {store_path}")

        # ==================================================================
        # 阶段 D：生成报告
        # ==================================================================
        report_text = ""
        try:
            report_writer = self.factory.create_report_writer()
            report_text = await generate_report(
                report_writer, store.to_dict(),
                flow_mode="debate", duration=0.0,
            )
        except Exception as e:
            self._logger.warning(f"ReportWriterAgent failed, falling back: {e}")

        if not report_text:
            report_text = fallback_render(store.to_dict(), flow_mode="debate")

        # 保存报告
        if task_id and report_text:
            import os
            report_path = os.path.join("output", "tasks", task_id, "report.md")
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report_text)

        # 构造返回结果
        summary = (
            f"Debate 审查完成：{store.finding_count} 条发现，"
            f"{len(store.debate_history)} 轮辩论，"
            f"共识={consensus_score:.2f}"
        )

        return ReviewResult(
            findings=list(store.findings),
            summary=summary,
            metadata={
                "debate_rounds": len(store.debate_history),
                "consensus_score": consensus_score,
                "max_rounds": max_rounds,
                "lead_decisions": len(store.decisions),
                "critic_challenges": len(store.challenges),
                "evidence_store_path": store_path,
            },
        )

    # ==================================================================
    # 共识分程序化计算
    # ==================================================================

    def _compute_consensus_score(self, store: EvidenceStore) -> float:
        """
        基于 EvidenceStore 实际状态计算程序化共识分。
        不依赖模型自报，保证单调递增、可复现。

        公式：consensus = 0.5 * decision_ratio + 0.3 * (1 - active_ratio) + 0.2 * round_engagement
        - decision_ratio: 已裁决 findings / 总 findings
        - active_ratio:   当前活跃 findings / 总 findings（越低越好）
        - round_engagement: min(debate_rounds / 3, 1.0)
        """
        total = store.finding_count
        if total == 0:
            return 1.0

        decided_ids = set()
        for d in store.decisions:
            decided_ids.add(d.finding_id)
        decision_ratio = len(decided_ids) / total

        active = len(store.get_active_findings())
        active_ratio = active / total

        round_engagement = min(len(store.debate_history) / 3.0, 1.0)

        score = (
            0.5 * decision_ratio
            + 0.3 * (1.0 - active_ratio)
            + 0.2 * round_engagement
        )

        if store.decisions or store.challenges or store.debate_history:
            score = max(score, 0.01)

        return round(min(score, 1.0), 4)

    # ==================================================================
    # Lead Controller Debate 模式调度
    # ==================================================================

    async def _run_lead_debate_round(
        self,
        lead: Agent,
        store: EvidenceStore,
        diff: str,
        pr_description: str,
        round_num: int,
    ) -> dict:
        """
        调用 Lead Controller 进行一轮 Debate 模式调度。
        返回解析后的调度结果字典。
        """
        # 精简 findings 为关键字段，避免 token 溢出
        findings_compact = []
        for f in store.findings:
            d = finding_to_dict(f)
            findings_compact.append({
                "id": d.get("id", ""),
                "severity": d.get("severity", ""),
                "title": d.get("title", "")[:120],
                "file_path": d.get("file_path", ""),
                "confidence": d.get("confidence", 0.5),
            })
        findings_json = json.dumps(findings_compact, ensure_ascii=False, indent=2)

        # 构造辩论历史摘要
        history_lines = []
        for r in store.debate_history:
            history_lines.append(
                f"第{r.round_number}轮 [{r.lead_action}] → {r.actor}: {r.result_summary[:100]}"
            )
        history_text = "\n".join(history_lines) if history_lines else "暂无历史轮次。"

        prompt = (
            f"## 当前审查发现（共 {store.finding_count} 条）\n"
            f"```json\n{findings_json}\n```\n\n"
            f"## 代码变更 (Diff)\n```\n{diff[:4000]}\n```\n\n"
            f"## 辩论历史（第 {round_num} 轮）\n{history_text}\n\n"
            f"请以 Debate 模式选择下一步动作（CHALLENGE/REBUTTAL/SUPPLEMENT/MERGE/ACCEPT/REJECT/FINISH）。\n"
            f"输出 JSON 对象：mode, action, target_finding_id, reason, assignee, consensus_score, summary。"
            f"当 action 为 MERGE 时，必须额外输出 merge_target_id（合并目标的 finding id）。\n"
        )

        try:
            msg = Msg(name="user", role="user",
                      content=[{"type": "text", "text": prompt}])
            t0 = time.time()
            result = await lead.reply(msg)
            elapsed_ms = int((time.time() - t0) * 1000)

            output_text = '{"mode":"debate","action":"FINISH","consensus_score":0.5}'
            if result and hasattr(result, 'content') and result.content:
                texts = []
                for block in result.content:
                    if hasattr(block, 'text') and block.text:
                        texts.append(block.text)
                output_text = ''.join(texts) or output_text

            self.transcript.log(
                step="lead_controller", agent="LeadController", action="debate_round",
                input_text=prompt, output_text=output_text,
                duration_ms=elapsed_ms,
                metadata={"round": round_num, "findings_count": store.finding_count},
            )

            return parse_lead_controller_output(output_text)
        except Exception as e:
            logger.warning(f"Lead Controller debate round failed: {e}")
            fallback_score = self._compute_consensus_score(store)
            return {"mode": "debate", "action": "FINISH", "consensus_score": fallback_score}

    # ==================================================================
    # Action 路由：根据 Lead Controller 的指令调度对应角色
    # ==================================================================

    async def _route_action(
        self,
        action: str,
        target_id: str,
        reason: str,
        lead_output: dict,
        critic: Agent,
        store: EvidenceStore,
        diff: str,
        round_num: int,
    ) -> dict:
        """
        根据 Lead Controller 选择的 action，路由到对应角色执行。
        返回 {"actor": 角色名, "summary": 执行摘要}
        """
        if action == "CHALLENGE":
            # 交给 Critic 质疑指定 finding
            return await self._action_challenge(critic, store, diff, target_id, reason)

        elif action == "REBUTTAL":
            # 交给对应 Reviewer 反驳 Critic 的质疑
            return await self._action_rebuttal(store, diff, target_id, reason)

        elif action == "SUPPLEMENT":
            # 补证：读取更多文件或搜索代码
            return await self._action_supplement(store, diff, target_id, reason)
        elif action == "MERGE":
            # 合并：Lead Controller 应指定 merge_target_id
            merge_target = lead_output.get("merge_target_id", "")
            if not merge_target:
                logger.warning(f"MERGE action missing merge_target_id, falling back to ACCEPT for {target_id}")
                await store.add_decision(Decision(
                    finding_id=target_id, action="ACCEPT",
                    reason=f"MERGE missing target, degraded to ACCEPT: {reason}",
                ))
                return {"actor": "LeadController", "summary": f"MERGE->ACCEPT {target_id}: missing merge_target_id"}
            return await self._action_merge(store, target_id, merge_target)

        elif action == "ACCEPT":
            # 接受该 finding
            await store.add_decision(Decision(
                finding_id=target_id, action="ACCEPT", reason=reason,
            ))
            return {"actor": "LeadController", "summary": f"接受 {target_id}"}

        elif action == "REJECT":
            # 拒绝该 finding（误报）
            await store.add_decision(Decision(
                finding_id=target_id, action="REJECT", reason=reason,
            ))
            await store.remove_finding(target_id)
            return {"actor": "LeadController", "summary": f"拒绝并移除 {target_id}"}

        else:
            logger.warning(f"Unknown action: {action}")
            return {"actor": "unknown", "summary": f"未知动作 {action}"}

    # ==================================================================
    # 各 Action 的具体执行逻辑
    # ==================================================================

    async def _action_challenge(
        self, critic: Agent, store: EvidenceStore,
        diff: str, target_id: str, reason: str,
    ) -> dict:
        """Critic 对指定 finding 进行质疑"""
        finding = store.get_finding(target_id)
        if not finding:
            return {"actor": "Critic", "summary": f"目标 {target_id} 不存在，跳过"}

        finding_json = json.dumps(finding_to_dict(finding), ensure_ascii=False, indent=2)
        prompt = (
            f"请对以下缺陷进行质疑验证。\n\n"
            f"## 目标缺陷\n```json\n{finding_json}\n```\n\n"
            f"## 代码变更 (Diff)\n```\n{diff[:4000]}\n```\n\n"
            f"## 质疑方向\n{reason}\n\n"
            f"输出包含 actions、new_findings、consensus_score 和 summary 的 JSON 对象。"
        )

        try:
            msg = Msg(name="user", role="user",
                      content=[{"type": "text", "text": prompt}])
            result = await critic.reply(msg)
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
            )

            parsed = self._extract_json(output_text)
            actions = parsed.get("actions", [])
            new_findings_raw = parsed.get("new_findings", [])

            # 记录质疑
            for a in actions:
                if isinstance(a, dict):
                    await store.add_challenge(Challenge(
                        finding_id=a.get("finding_id", target_id),
                        challenger="Critic",
                        action=a.get("action", "CHALLENGE"),
                        reason=a.get("reason", ""),
                        new_severity=a.get("new_severity", ""),
                        merge_target_id=a.get("merge_target_id", ""),
                    ))

            # 应用 actions
            updated = apply_debate_actions(list(store.findings), actions, new_findings_raw)
            store.findings = updated

            action_count = len(actions)
            return {
                "actor": "Critic",
                "summary": f"质疑 {target_id}: {action_count} 条操作，剩余 {store.finding_count} 条 findings",
            }
        except Exception as e:
            logger.warning(f"Critic challenge failed: {e}")
            return {"actor": "Critic", "summary": f"质疑失败: {e}"}

    async def _action_rebuttal(
        self, store: EvidenceStore,
        diff: str, target_id: str, reason: str,
    ) -> dict:
        """
        Reviewer 对 Critic 的质疑进行反驳。
        从 finding.sources 中找到原始 Reviewer 角色，调用其反驳。
        """
        finding = store.get_finding(target_id)
        if not finding:
            return {"actor": "Reviewer", "summary": f"目标 {target_id} 不存在，跳过"}

        # 从 sources 推断原始 Reviewer 角色
        source_role = finding.sources[0] if finding.sources else "security_expert"
        # 确保 source_role 是合法的 Reviewer 角色
        from src.agents.reviewer_agent import REVIEWER_ROLES as SCANNER_ROLES
        if source_role not in SCANNER_ROLES:
            source_role = "security_expert"  # 兜底

        reviewer_agents = self.factory.create_scanners(roles=[source_role])
        reviewer = list(reviewer_agents.values())[0]

        # 构造反驳 prompt
        challenges_for_finding = [
            c for c in store.challenges if c.finding_id == target_id
        ]
        challenge_text = "\n".join(
            f"- [{c.action}] {c.reason}" for c in challenges_for_finding
        ) if challenges_for_finding else "无具体质疑记录"

        finding_json = json.dumps(finding_to_dict(finding), ensure_ascii=False, indent=2)
        prompt = (
            f"你是 {source_role}，请对以下质疑进行反驳。\n\n"
            f"## 原始缺陷\n```json\n{finding_json}\n```\n\n"
            f"## 收到的质疑\n{challenge_text}\n\n"
            f"## 代码变更 (Diff)\n```\n{diff[:4000]}\n```\n\n"
            f"请提供反驳理由和补充证据。输出 JSON 数组格式的补充 findings（如无则输出 []）。"
        )

        try:
            msg = Msg(name="user", role="user",
                      content=[{"type": "text", "text": prompt}])
            result = await reviewer.reply(msg)
            output_text = "[]"
            if result and hasattr(result, 'content') and result.content:
                texts = []
                for block in result.content:
                    if hasattr(block, 'text') and block.text:
                        texts.append(block.text)
                output_text = ''.join(texts) or output_text

            self.transcript.log(
                step="rebuttal", agent=source_role, action="rebuttal",
                input_text=prompt, output_text=output_text,
            )

            # 解析补充 findings
            new_findings = self._parse_findings(output_text)
            if new_findings:
                await store.add_findings(new_findings)

            return {
                "actor": source_role,
                "summary": f"反驳 {target_id}: 提供 {len(new_findings)} 条补充证据",
            }
        except Exception as e:
            logger.warning(f"Rebuttal failed: {e}")
            return {"actor": source_role, "summary": f"反驳失败: {e}"}

    async def _action_supplement(
        self, store: EvidenceStore,
        diff: str, target_id: str, reason: str,
    ) -> dict:
        """
        补证：调用工具（read_file / search_code）补充证据。
        从 Critic 的 suggest_files 中获取需要查看的文件。
        """
        finding = store.get_finding(target_id)
        if not finding:
            return {"actor": "Tool", "summary": f"目标 {target_id} 不存在，跳过"}

        # 从 Critic 的质疑记录中获取建议查看的文件
        suggest_files = []
        for c in store.challenges:
            if c.finding_id == target_id and c.metadata.get("suggest_files"):
                suggest_files = c.metadata["suggest_files"]
                break

        # 如果没有建议文件，基于 finding 的 file_path 补证
        if not suggest_files and finding.file_path:
            suggest_files = [finding.file_path]

        supplement_evidence = []
        for filepath in suggest_files[:3]:  # 最多查看 3 个文件
            try:
                # 调用 read_file 工具
                toolkit = self.factory.toolkit
                if toolkit:
                    # 通过 Agent 调用工具
                    prompt = f"请读取文件 {filepath} 的内容"
                    msg = Msg(name="user", role="user",
                              content=[{"type": "text", "text": prompt}])
                    # 使用一个临时 Reviewer 来调用工具
                    temp_agent = self.factory.create_scanners(roles=["security_expert"])
                    reviewer = list(temp_agent.values())[0]
                    result = await reviewer.reply(msg)
                    if result and hasattr(result, 'content') and result.content:
                        for block in result.content:
                            if hasattr(block, 'text') and block.text:
                                supplement_evidence.append(block.text[:500])
            except Exception as e:
                logger.warning(f"Supplement read {filepath} failed: {e}")

        # 将补充证据附加到 finding
        if supplement_evidence and finding:
            combined = "\n---\n".join(supplement_evidence)
            finding.evidence = f"{finding.evidence}\n[补充证据]\n{combined}" if finding.evidence else combined

        return {
            "actor": "Tool",
            "summary": f"补证 {target_id}: 查看 {len(suggest_files)} 个文件，获取 {len(supplement_evidence)} 条证据",
        }

    async def _action_merge(
        self, store: EvidenceStore,
        source_id: str, target_id: str,
    ) -> dict:
        """合并两个 findings"""
        success = await store.merge_findings(source_id, target_id)
        if success:
            await store.add_decision(Decision(
                finding_id=source_id, action="MERGE",
                reason=f"合并到 {target_id}", merge_target_id=target_id,
            ))
            return {"actor": "LeadController", "summary": f"合并 {source_id} → {target_id}"}
        else:
            return {"actor": "LeadController", "summary": f"合并失败: {source_id} 或 {target_id} 不存在"}

