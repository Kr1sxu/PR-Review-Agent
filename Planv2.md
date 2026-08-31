# PR-Review Agent v2 架构改造计划

> 基于 Multi-Agent Controller 架构，重构审查流程。
> 将现有 Pipeline + Debate 模式升级为 Lead Controller 调度的多角色协作体系。
> 每完成一项，在对应 checklist 上打勾。
> 每完成一个阶段后停下来，报告给用户，等待用户命令继续。
> 编写的代码必要部分需要加上中文注释
---

## 架构变更总览

### 角色对照（v1 → v2）

| v1 角色 | v2 角色 | 操作 |
|---------|---------|------|
| Scanner x6 | Reviewer x5 + company_policy_reviewer（独立） | 拆分重组 |
| Merger | **删除** | 职能由 Lead Controller + ReportWriterAgent 分担 |
| Debater | Critic | 重命名 + prompt 优化 |
| (无) | Lead Controller | **新建** |
| ReportRenderer（纯模板） | ReportWriterAgent（LLM Agent） | 升级 |
| Judge | Judge | 保留不动 |

### 流程对照（v1 → v2）

**Council 模式（v1 → v2）**
`
v1: Scanner x6 并行 → Merger 合并 → 输出
v2: Reviewer x5 并行 + company_policy_reviewer → Lead Controller 裁决 → Critic 质疑 → ReportWriterAgent 输出
`

**Debate 模式（v1 → v2）**
`
v1: Scanner x6 → Merger → Debater 多轮（Debater 驱动 actions）→ 输出
v2: Reviewer x5 + company_policy_reviewer → Lead Controller 动态调度（质疑/反驳/补证/合并/接收/拒绝）→ ReportWriterAgent 输出
`

---

## 阶段一：基础设施 — EvidenceStore

**目标**：新建共享证据仓库，替代原有 findings 列表传递方式。

### 1.1 新建 src/flows/evidence_store.py

- [√] 实现 EvidenceStore 数据类
  - indings: List[Finding] — 当前活跃的缺陷列表
  - policy_references: List[dict] — company_policy_reviewer 命中的规范条目
  - challenges: List[dict] — Critic 质疑记录
  - decisions: List[dict] — Lead Controller 裁决记录
  - debate_history: List[dict] — 多轮辩论历史（Debate 模式专用）
- [√] 实现方法
  - dd_finding(finding) — 添加/更新 finding
  - 
emove_finding(finding_id) — 移除 finding
  - merge_findings(source_id, target_id) — 合并两个 findings
  - dd_policy_reference(ref) — 添加政策引用
  - dd_challenge(challenge) — 记录质疑
  - dd_decision(decision) — 记录裁决
  - 	o_dict() -> dict — 序列化
  - save_json(path) — 持久化到磁盘
  - load_json(path) -> EvidenceStore — 从磁盘加载
- [√] 输出文件路径：output/tasks/{task_id}/evidence_store.json

**关联文档更新**：
- [√] 新建 src/flows/README.md 更新：新增 EvidenceStore 说明
- [√] 项目 README.md 输出文件说明中新增 evidence_store.json

---

## 阶段二：新建 Agent — Lead Controller

**目标**：实现动态调度核心，替代硬编码的流程编排。

### 2.1 新建 src/agents/lead_controller.py

- [√] 定义 LEAD_CONTROLLER_SYSTEM_PROMPT
  - 角色定义：你是 PR 审查流程的总指挥
  - **Council 模式指令**：审查完 findings 后，对每条做 ACCEPT / REJECT / DOWNGRADE / SUPPLEMENT 裁决
  - **Debate 模式指令**：每轮动态选择下一步 action：
    - CHALLENGE → 交给 Critic 质疑指定 finding
    - REBUTTAL → 交给 Reviewer 对质疑进行反驳
    - SUPPLEMENT → 指派补证（读取更多文件/运行测试）
    - MERGE → 合并相似 findings
    - ACCEPT → 接受该 finding
    - REJECT → 拒绝该 finding
  - 输出格式：JSON，包含 ction、	arget_finding_id、
eason、consensus_score
- [√] 实现 create_lead_controller_agent(model, toolkit) 工厂函数
- [√] 实现 Lead Controller 的输出解析逻辑

**关联文档更新**：
- [√] src/agents/README.md 更新：新增 Lead Controller 角色说明

---

## 阶段三：新建 Agent — ReportWriterAgent

**目标**：将模板渲染升级为 LLM 驱动的智能报告生成。

### 3.1 新建 src/agents/report_writer.py

- [√] 定义 REPORT_WRITER_SYSTEM_PROMPT
  - 角色定义：你是专业的代码审查报告撰写专家
  - 输入：EvidenceStore（findings + policy_references + 裁决记录）
  - 职责：
    - 将结构化 findings 组织为可读的叙述性报告
    - 自动为每条 finding 补充上下文说明
    - 在报告中嵌入 policy_references（公司规范引用）
    - 按严重级别分组，生成执行摘要
  - 输出：标准化 Markdown 报告
- [√] 实现 create_report_writer_agent(model) 工厂函数
- [√] 保留现有 ReportRenderer 作为离线降级方案（无模型时回退到模板渲染）

**关联文档更新**：
- [√] src/report/README.md 更新：新增 ReportWriterAgent 说明，ReportRenderer 标注为离线降级
- [√] src/agents/README.md 更新：新增 ReportWriterAgent 角色说明

---

## 阶段四：改造现有 Agent

**目标**：重组 Scanner、改造 Debater、删除 Merger。

### 4.1 修改 src/agents/scanner_agent.py → 重命名为 reviewer_agent.py + 公司策略审查员独立为 company_policy_reviewer.py（v2.1 实际执行）

- [√] 将 company_policy_reviewer 从 SCANNER_ROLES 字典中独立出来
  - 新建独立常量 COMPANY_POLICY_REVIEWER_ROLE
  - 新建独立工厂函数 create_company_policy_reviewer(model, toolkit, rag_context, skill_context)
  - SCANNER_ROLES 仅保留 5 个 Reviewer 角色
- [√] Reviewer 角色 prompt 微调
  - 在 prompt 中明确角色名改为 "Reviewer"（不再叫 "Scanner"）
  - 输出格式要求不变（JSON findings 数组）

### 4.2 修改 src/agents/debater_agent.py → 重命名为 src/agents/critic_agent.py

- [√] 重命名文件
- [√] 更新 DEBATER_SYSTEM_PROMPT → CRITIC_SYSTEM_PROMPT
  - 角色名从"辩论参与者和仲裁者"改为"审查质疑专家"
  - 移除 ACCEPT 动作（Critic 只负责质疑，不负责裁决）
  - 保留 CHALLENGE / DOWNGRADE / MERGE / REJECT 动作
  - 新增"补充证据"能力：指出证据不足时，建议需要查看哪些文件
- [√] 更新函数名 create_debater_agent → create_critic_agent

### 4.3 删除 Merger 相关文件

- [√] 删除 src/agents/merger_agent.py
- [√] 删除 src/flows/programmatic_merger.py
- [√] 清理所有引用 Merger 的 import

### 4.4 修改 src/agents/agent_factory.py

- [√] 新增 create_lead_controller() 方法
- [√] 新增 create_report_writer() 方法
- [√] 新增 create_company_policy_reviewer() 方法
- [√] 重命名 create_debater() → create_critic()
- [√] 删除 create_merger() 方法
- [√] 更新 create_all() 返回值结构

**关联文档更新**：
- [√] src/agents/README.md 全面更新：角色清单、工厂方法示例、设计说明

---

## 阶段五：重构流程

**目标**：用新版 Council / Debate 流程替换旧版，集成 EvidenceStore。

### 5.1 修改 src/flows/council_flow.py（原地替换）

- [√] 删除旧的 CouncilFlow 实现
- [√] 重写 CouncilFlow
  - 流程：Reviewer x5 并行 → company_policy_reviewer → Lead Controller 裁决 → Critic 质疑 → Lead Controller 最终确认 → 写入 EvidenceStore
  - 使用 EvidenceStore 作为 findings 的单一数据源
  - Lead Controller 裁决结果写入 EvidenceStore.decisions
  - Critic 质疑结果写入 EvidenceStore.challenges

### 5.2 修改 src/flows/debate_flow.py（原地替换）

- [√] 删除旧的 DebateFlow 实现
- [√] 重写 DebateFlow
  - 流程：Reviewer x5 并行 → company_policy_reviewer → 多轮 Lead Controller 调度
  - 每轮：Lead Controller 选择 action → 执行对应角色 → 更新 EvidenceStore → 判断是否继续
  - 终止条件：consensus_score >= 0.8 或达到 max_rounds
  - action 路由：
    - CHALLENGE → 调用 Critic
    - REBUTTAL → 调用对应 Reviewer
    - SUPPLEMENT → 调用工具（read_file / search_code / run_tests）
    - MERGE → EvidenceStore.merge_findings()
    - ACCEPT → EvidenceStore 标记采纳
    - REJECT → EvidenceStore 移除

### 5.3 修改 src/flows/agentic_flow.py

- [√] 更新继承关系：AgenticFlow 继承新版 DebateFlow
- [√] 移除旧的 Merger 引用

### 5.4 修改 src/flows/base_flow.py

- [√] 更新 pply_debate_actions() 函数适配新结构
- [√] ReviewResult 新增 evidence_store_path 字段（指向持久化的 EvidenceStore）

### 5.5 删除旧文件

- [√] 确认 src/flows/programmatic_merger.py 已删除（阶段四）
- [√] 清理 __init__.py 中的旧 import

**关联文档更新**：
- [√] src/flows/README.md 全面更新：流程清单、Council/Debate 新版说明、EvidenceStore 说明

---

## 阶段六：报告生成改造

**目标**：Council / Debate 流程末尾接入 ReportWriterAgent。

### 6.1 修改 src/flows/council_flow.py 和 src/flows/debate_flow.py

- [√] 在流程末尾调用 ReportWriterAgent
  - 输入：EvidenceStore.to_dict()
  - 输出：标准化 Markdown 报告（含 policy_references）
  - 离线降级：回退到 ReportRenderer.render()

### 6.2 保留 src/report/report_renderer.py

- [√] 不删除，作为离线降级方案
- [√] 新增 
ender_from_evidence_store(evidence_store_dict) 方法，兼容新数据结构

**关联文档更新**：
- [√] src/report/README.md 更新：说明 ReportWriterAgent 在线 / ReportRenderer 离线的双轨机制

---

## 阶段七：调度层与入口适配

**目标**：让 TaskManager 和 CLI / Web 支持新模式。

### 7.1 修改 src/scheduler/task_manager.py

- [√] 更新 _create_flow() 方法
  - 移除 Merger 相关逻辑
  - 确认 council / debate / gentic 使用新版 flow
  - simple 模式不变
- [√] 更新 start_task() 中的 EvidenceStore 处理
  - 流程结束后保存 evidence_store.json 到 output/tasks/{task_id}/
  - Judge 读取 evidence_store.json 作为评分输入

### 7.2 修改 src/main.py

- [√] 确认 --mode 参数选项：simple / council / debate / gentic（不变）
- [√] 更新帮助文本中的模式说明

### 7.3 修改 src/web/routes_task.py

- [√] 确认前端模式选择器兼容（无需新增模式，只是内部流程变了）

### 7.4 修改 src/judge/judge_runner.py

- [√] 更新 _build_prompt() 方法
  - 除了 findings，还读取 policy_references
  - 新增评分维度考虑："企业规范覆盖度"（可选，或融入现有六维）

**关联文档更新**：
- [√] src/scheduler/README.md 更新：说明 task_manager 对新版 flow 的调度方式
- [√] src/judge/README.md 更新：说明 Judge 读取 EvidenceStore 的方式

---

## 阶段八：配置与 Prompt 管理

**目标**：新增的 prompt 统一管理。

### 8.1 新建 Prompt 文件

- [√] config/prompts/lead_controller.txt — Lead Controller system prompt
- [√] config/prompts/report_writer.txt — ReportWriterAgent system prompt
- [√] config/prompts/critic.txt — 替代原 config/prompts/debater.txt

### 8.2 修改配置

- [√] config/settings.yaml 更新
  - 新增 lead_controller 相关参数（max_debate_rounds 等）
  - 新增 
eport_writer 相关参数
  - 移除 merger 相关参数（如有）

**关联文档更新**：
- [√] README.md 更新：config/prompts 说明

---

## 阶段九：测试

**目标**：确保新版流程正确运行。

### 9.1 新建测试文件

- [√] 	ests/test_evidence_store.py — EvidenceStore 增删改查、持久化、加载
- [√] 	ests/test_lead_controller.py — Lead Controller 输出解析、action 路由
- [√] 	ests/test_report_writer.py — ReportWriterAgent 报告生成
- [√] 	ests/test_council_v2.py — 新版 Council 流程端到端
- [√] 	ests/test_debate_v2.py — 新版 Debate 流程端到端

### 9.2 修改现有测试

- [√] 	ests/test_agents.py — 适配角色重命名（Scanner→Reviewer、Debater→Critic、删除 Merger）
- [√] 	ests/test_flows.py — 适配新版流程
- [√] 	ests/test_tools.py — 确认工具层无变化

**关联文档更新**：
- [√] 无需更新模块 README，但项目 README 的测试运行命令说明保持不变

---

## 阶段十：文档收尾

### 10.1 更新项目 README.md

- [√] 更新架构图（v2 架构）
- [√] 更新审查模式说明表
- [√] 更新项目结构说明（新增/删除的文件）
- [√] 更新输出文件说明（新增 evidence_store.json）
- [√] 更新技术选型表（如有变化）
- [√] 新增修改记录章节

### 10.2 更新模块 README

- [√] src/agents/README.md — 角色清单、工厂方法、设计说明
- [√] src/flows/README.md — 流程清单、Council/Debate 新版说明、EvidenceStore
- [√] src/report/README.md — ReportWriterAgent + ReportRenderer 双轨机制
- [√] src/scheduler/README.md — 新版调度说明
- [√] src/judge/README.md — EvidenceStore 读取说明
- [√] src/tools/README.md — 确认无变化（可跳过）

---

## 文件变更汇总

### 新建文件（6 个）

| 文件 | 模块 | 说明 |
|------|------|------|
| src/flows/evidence_store.py | flows | EvidenceStore 共享证据仓库 |
| src/agents/lead_controller.py | agents | Lead Controller Agent |
| src/agents/report_writer.py | agents | ReportWriterAgent |
| src/agents/critic_agent.py | agents | Critic（替代 debater_agent.py） |
| config/prompts/lead_controller.txt | config | Lead Controller prompt |
| config/prompts/report_writer.txt | config | ReportWriterAgent prompt |

### 修改文件（10 个）

| 文件 | 模块 | 变更 |
|------|------|------|
| src/agents/reviewer_agent.py | agents | Reviewer x5（v2.1 重命名），SCANNER_ROLES 作为别名保留 |
| src/agents/company_policy_reviewer.py | agents | 公司策略审查员独立文件（v2.1 新建） |
| src/agents/agent_factory.py | agents | 新增 3 个工厂方法，删除 merger |
| src/flows/council_flow.py | flows | 原地重写，接入 Lead Controller + EvidenceStore |
| src/flows/debate_flow.py | flows | 原地重写，Lead Controller 驱动多轮调度 |
| src/flows/agentic_flow.py | flows | 适配新版 DebateFlow |
| src/flows/base_flow.py | flows | ReviewResult 新增 evidence_store_path |
| src/scheduler/task_manager.py | scheduler | 适配新版 flow，保存 EvidenceStore |
| src/main.py | 入口 | 更新帮助文本 |
| src/judge/judge_runner.py | judge | 读取 policy_references |
| config/settings.yaml | config | 新增参数 |

### 删除文件（2 个）

| 文件 | 模块 | 原因 |
|------|------|------|
| src/agents/merger_agent.py | agents | 职能由 Lead Controller + ReportWriterAgent 分担 |
| src/flows/programmatic_merger.py | flows | 同上 |

### 重命名文件（1 个）

| 原文件 | 新文件 | 说明 |
|--------|--------|------|
| src/agents/debater_agent.py | 已删除（v2.1） | 功能由 critic_agent.py 替代 |
| config/prompts/debater.txt | config/prompts/critic.txt | prompt 文件跟随重命名 |

---

## 实施顺序与依赖关系

`
阶段一（EvidenceStore）          ← 无依赖，最先做
    ↓
阶段二（Lead Controller）        ← 依赖 EvidenceStore 数据结构
    ↓
阶段三（ReportWriterAgent）      ← 依赖 EvidenceStore 数据结构
    ↓
阶段四（改造现有 Agent）          ← 依赖阶段二、三的工厂方法
    ↓
阶段五（重构流程）               ← 依赖阶段一～四全部完成
    ↓
阶段六（报告生成改造）            ← 依赖阶段五的流程
    ↓
阶段七（调度层与入口适配）        ← 依赖阶段五、六
    ↓
阶段八（配置与 Prompt 管理）      ← 可与阶段五～七并行
    ↓
阶段九（测试）                   ← 依赖阶段五～七全部完成
    ↓
阶段十（文档收尾）               ← 最后做
`

---

## 风险与注意事项

| 风险 | 应对 |
|------|------|
| Lead Controller 输出解析失败 | 实现 robust 的 JSON 提取 + 兜底默认 action（ACCEPT） |
| Debate 模式无限循环 | 硬编码 max_rounds 上限 + consensus_score 阈值双保险 |
| company_policy_reviewer 并行执行与 EvidenceStore 写入冲突 | 使用 asyncio.Lock 保护写入 |
| ReportWriterAgent 输出格式不稳定 | 保留 ReportRenderer 作为离线降级 |
| 删除 Merger 后 imports 报错 | 阶段四统一清理，阶段九测试验证 |



