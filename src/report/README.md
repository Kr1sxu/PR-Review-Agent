# 报告模块 — PR-Review Agent v2

结构化缺陷数据管理和报告生成。v2 支持 LLM Agent 在线生成 + 模板离线降级双轨机制。

## 模块清单

| 文件 | 功能 |
|------|------|
| findings.py | FindingData / FindingsCollection 数据类，JSON 读写，校验，排序/过滤 |
| report_renderer.py | 离线降级方案：将检查发现渲染为按严重性分组的结构化 Markdown 报告 |

## v2 报告生成机制

| 模式 | 使用组件 | 说明 |
|------|---------|------|
| 在线 | ReportWriterAgent（`src/agents/report_writer.py`） | LLM 驱动，支持叙述性描述、政策引用嵌入、裁决记录展示 |
| 离线 | ReportRenderer（本模块） | 模板渲染，无模型调用，自动追加 policy_references |

流程默认使用 ReportWriterAgent；模型不可用时自动降级到 ReportRenderer。

## 使用示例

```python
from src.report.findings import FindingsCollection, FindingData
from src.report.report_renderer import ReportRenderer

# 从流结果创建集合
collection = FindingsCollection.from_review_findings(flow_result.findings)

# 保存/加载 JSON
collection.save_json("output/findings.json")
collection = FindingsCollection.load_json("output/findings.json")

# 离线渲染 Markdown 报告（降级方案）
renderer = ReportRenderer(title="PR 审查报告")
report_md = renderer.render(collection, flow_mode="debate", duration=120.5)

# 在线报告生成（v2 推荐）
from src.agents.report_writer import generate_report
from src.flows.evidence_store import EvidenceStore
store = EvidenceStore.load_json("output/tasks/{task_id}/evidence_store.json")
report_md = await generate_report(report_writer_agent, store.to_dict(), flow_mode="debate")
```
