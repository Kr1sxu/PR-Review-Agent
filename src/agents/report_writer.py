"""
Report Writer Agent - PR-Review Agent v2
LLM 驱动的标准化报告生成，替代原有模板渲染。
接收 EvidenceStore 数据，生成含 policy_references 的结构化 Markdown 报告。
离线降级：模型不可用时回退到 ReportRenderer 模板渲染。
"""

import logging
from typing import Optional

from agentscope.agent._agent import Agent
from agentscope.model._base import ChatModelBase

logger = logging.getLogger(__name__)

# ======================================================================
# ReportWriterAgent 系统提示词
# ======================================================================

REPORT_WRITER_SYSTEM_PROMPT = """你是一位专业的代码审查报告撰写专家。

## 任务
将结构化的审查证据数据（EvidenceStore）转化为清晰、专业、可操作的 Markdown 审查报告。

## 输入数据
你会收到一个 JSON 对象，包含：
- findings：审查发现列表（含 id、category、severity、title、description、evidence、suggestion 等）
- policy_references：公司规范引用（含 policy_area、rule_text、matched_finding_ids）
- challenges：质疑记录
- decisions：裁决记录
- summary：统计摘要

## 报告结构要求

### 1. 执行摘要
- 一句话总结审查结论（通过/需修改/需重大修改）
- 发现总数、各级别分布
- 关键风险提示（如有 P0/P1 级别问题）

### 2. 风险总览表
| 严重级别 | 数量 | 代表性问题 |
按级别从高到低排列，每级列出最具代表性的 1-2 个问题

### 3. 详细发现（按严重级别分组）
每条 finding 包含：
- 标题 + ID
- 严重级别 + 置信度
- 文件路径 + 行号
- 问题描述
- 代码证据（如有）
- 修复建议
- 关联的公司规范引用（从 policy_references 中匹配）

### 4. 公司规范合规（如有 policy_references）
- 列出本次审查涉及的公司规范条目
- 每条规范关联的 findings

### 5. 裁决记录（如有 decisions）
- Lead Controller 的裁决摘要
- 被接受/拒绝/降级的 findings 统计

### 6. 附录
- 审查模式、耗时、工具使用统计

## 写作原则
1. 客观中立：基于证据描述，不夸大不缩小
2. 可操作：每条 finding 必须有明确的修复建议
3. 结构清晰：使用 Markdown 标题、表格、代码块
4. 合规引用：涉及公司规范时必须标注 policy_reference
5. 中文撰写
"""


def create_report_writer_agent(model: ChatModelBase) -> Agent:
    """
    创建 ReportWriterAgent 实例。
    :param model: Chat model 实例
    :return: Agent 实例
    """
    agent = Agent(
        name="report_writer",
        system_prompt=REPORT_WRITER_SYSTEM_PROMPT,
        model=model,
    )
    logger.info("Created report writer agent")
    return agent


async def generate_report(
    report_writer: Agent,
    evidence_store_dict: dict,
    flow_mode: str = "",
    duration: float = 0.0,
) -> str:
    """
    使用 ReportWriterAgent 生成标准化 Markdown 报告。
    :param report_writer: ReportWriterAgent 实例
    :param evidence_store_dict: EvidenceStore.to_dict() 的输出
    :param flow_mode: 流程模式标识（council / debate / agentic）
    :param duration: 审查耗时（秒）
    :return: Markdown 格式的报告字符串，失败返回空字符串
    """
    from agentscope.message._base import Msg
    import json

    # 注入流程元信息（审查模式、耗时）
    prompt_data = dict(evidence_store_dict)
    prompt_data["_meta"] = {
        "flow_mode": flow_mode,
        "duration_seconds": round(duration, 2),
    }

    # 构造 prompt：要求模型根据 EvidenceStore 数据生成完整 Markdown 报告
    prompt = (
        f"请根据以下审查证据数据生成标准化 Markdown 审查报告。\n\n"
        f"## 审查证据数据\n"
        f"```json\n{json.dumps(prompt_data, ensure_ascii=False, indent=2)}\n```\n\n"
        f"请严格按照报告结构要求输出完整的 Markdown 报告。"
    )

    try:
        msg = Msg(name="user", role="user",
                  content=[{"type": "text", "text": prompt}])
        result = await report_writer.reply(msg)

        # 从模型响应中提取文本内容
        if result and hasattr(result, 'content') and result.content:
            texts = []
            for block in result.content:
                if hasattr(block, 'text') and block.text:
                    texts.append(block.text)
            report_text = ''.join(texts)
            if report_text.strip():
                logger.info(f"ReportWriterAgent generated report ({len(report_text)} chars)")
                return report_text

        logger.warning("ReportWriterAgent returned empty response")
        return ""

    except Exception as e:
        logger.error(f"ReportWriterAgent failed: {e}")
        return ""


def fallback_render(evidence_store_dict: dict, flow_mode: str = "", duration: float = 0.0) -> str:
    """
    离线降级方案：使用 ReportRenderer 模板渲染报告。
    当 ReportWriterAgent 不可用（模型离线/调用失败）时自动调用。
    会自动追加 policy_references 章节（模板渲染原本不支持）。
    :param evidence_store_dict: EvidenceStore.to_dict() 的输出
    :param flow_mode: 流程模式标识
    :param duration: 审查耗时（秒）
    :return: Markdown 格式的报告字符串
    """
    from src.report.report_renderer import ReportRenderer
    from src.report.findings import FindingsCollection, FindingData

    # 将 EvidenceStore 中的 findings 转换为 FindingsCollection（兼容现有渲染器）
    collection = FindingsCollection()
    for item in evidence_store_dict.get("findings", []):
        fd = FindingData(
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
        )
        collection.add(fd)

    # 使用模板渲染器生成基础报告
    renderer = ReportRenderer()
    report = renderer.render(collection, flow_mode=flow_mode, duration=duration)

    # 手动追加 policy_references 章节（模板渲染器不支持此功能）
    policy_refs = evidence_store_dict.get("policy_references", [])
    if policy_refs:
        report += "\n## 公司规范引用\n\n"
        for ref in policy_refs:
            report += f"- **{ref.get('policy_label', '')}**：{ref.get('rule_text', '')[:200]}\n"
        report += "\n"


    # 追加裁决记录摘要（模板渲染器不支持）
    decisions = evidence_store_dict.get('decisions', [])
    if decisions:
        report += '\n## 裁决记录\n\n'
        report += f'共 {len(decisions)} 条裁决：\n\n'
        for d in decisions:
            action = d.get('action', '')
            fid = d.get('finding_id', '')
            reason = d.get('reason', '')[:100]
            report += f'- [{action}] {fid}：{reason}\n'
        report += '\n'

    logger.info(f"Fallback report rendered ({len(report)} chars)")
    return report
