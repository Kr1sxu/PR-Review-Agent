# 流程模块 — PR-Review Agent v2

v2 架构下三种审查流程 + 共享证据仓库，统一由 BaseFlow 接口驱动。

## 流程清单

| 流程 | 文件 | 说明 |
|------|------|------|
| BaseFlow | base_flow.py | 抽象基类，定义统一的 execute() 接口 |
| SimpleFlow | simple_flow.py | 基于规则的正则扫描，无模型调用，离线降级方案 |
| CouncilFlow | council_flow.py | v2：Reviewer x5 并行 → company_policy_reviewer → Lead Controller 裁决 → Critic 质疑 → ReportWriterAgent 输出 |
| DebateFlow | debate_flow.py | v2：Lead Controller 动态调度多轮博弈（质疑/反驳/补证/合并/接收/拒绝）→ ReportWriterAgent 输出 |
| AgenticFlow | agentic_flow.py | v2：扩展 Debate 流程，预留自主特性扩展点 |
| EvidenceStore | evidence_store.py | v2 新增：共享证据仓库，所有角色的数据中枢 |

## v2 核心变化

- **Merger 已删除**：合并职责由程序化去重（`_programmatic_merge`）替代
- **Lead Controller 调度**：Debate 模式由 Lead Controller 主导，替代原 Debater 驱动
- **EvidenceStore 中枢**：所有数据通过 EvidenceStore 流转，持久化到磁盘
- **ReportWriterAgent 输出**：优先使用 LLM 生成报告，降级到模板渲染

## 流程对比（v1 → v2）

### Council 模式
```
v1: Scanner x6 并行 → Merger 合并 → 输出
v2: Reviewer x5 并行 + company_policy_reviewer → 程序化合并
    → Lead Controller 裁决 → Critic 质疑 → Lead Controller 最终确认
    → EvidenceStore 持久化 → ReportWriterAgent 输出
```

### Debate 模式
```
v1: Scanner x6 → Merger → Debater 多轮（Debater 驱动 actions）→ 输出
v2: Reviewer x5 + company_policy_reviewer → 程序化合并 → 写入 EvidenceStore
    → Lead Controller 动态调度（CHALLENGE/REBUTTAL/SUPPLEMENT/MERGE/ACCEPT/REJECT/FINISH）
    → EvidenceStore 持久化 → ReportWriterAgent 输出
```

## EvidenceStore

v2 新增的核心数据结构，替代原有 findings 列表传递方式。

### 数据组成

| 字段 | 写入者 | 说明 |
|------|--------|------|
| `findings` | Reviewer x5、Lead Controller | 当前活跃的缺陷列表 |
| `policy_references` | company_policy_reviewer | 命中的公司规范条目 |
| `challenges` | Critic | 质疑记录 |
| `decisions` | Lead Controller | 裁决记录 |
| `debate_history` | Lead Controller | 多轮辩论历史（Debate 模式专用） |

### 持久化

流程结束后自动保存到 `output/tasks/{task_id}/evidence_store.json`，
供 Judge 评分和事后复盘使用。

### 并发安全

通过 `asyncio.Lock` 保护写入操作，支持并行 Reviewer 安全写入。

## 使用示例

```python
from src.flows.simple_flow import SimpleFlow
from src.flows.council_flow import CouncilFlow
from src.flows.debate_flow import DebateFlow
from src.agents.agent_factory import AgentFactory

# Simple 模式（离线，无需模型）
simple = SimpleFlow()
result = await simple.execute(diff, pr_description)

# Council 模式（v2 新版）
factory = AgentFactory(model=mimo_model)
council = CouncilFlow(agent_factory=factory)
result = await council.execute(diff, pr_description, config={"task_id": "abc123"})

# Debate 模式（v2 新版，核心流程）
debate = DebateFlow(agent_factory=factory, max_rounds=3)
result = await debate.execute(diff, pr_description, config={"task_id": "abc123"})

# 读取 EvidenceStore（复盘）
from src.flows.evidence_store import EvidenceStore
store = EvidenceStore.load_json("output/tasks/abc123/evidence_store.json")
print(store.to_dict())
```

## 结果结构

所有流程统一返回 `ReviewResult`，包含：
- `flow_mode`：流程标识
- `findings`：`Finding` 对象列表
- `summary`：人类可读摘要
- `duration_seconds`：执行耗时
- `offline`：是否处于离线模式
- `metadata`：流程特有附加数据
- `evidence_store_path`：EvidenceStore 持久化路径（v2 新增）
