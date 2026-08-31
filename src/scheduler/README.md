# 调度模块 — PR-Review Agent v2

异步任务管理，连接 Web/CLI 入口与流程引擎。

## 模块清单

| 文件 | 功能 |
|------|------|
| task_manager.py | WebTaskManager：异步任务队列、生命周期管理、状态持久化 |

## v2 变更

- 流程内部处理 EvidenceStore 持久化和报告生成，task_manager 不再重复渲染
- `_build_judge_input_from_store()`：从 EvidenceStore 构造 Judge 输入（含 policy_references）
- 任务执行时将 `task_id` 传入流程 config，流程自动保存 `evidence_store.json`

## 任务生命周期

```
pending -> running -> completed
                   -> failed
         -> cancelled
```

## 使用示例

```python
from src.scheduler.task_manager import WebTaskManager

manager = WebTaskManager(output_dir="./output/tasks", max_concurrent=3)

# 创建任务
task = manager.create_task(
    mode="debate",           # simple / council / debate / agentic
    repo_path="/path/to/repo",
    base_commit="main",
    target_commit="feature",
    pr_description="新增支付处理逻辑",
    rag_enabled=True,
    max_rounds=3,
)

# 启动执行（异步）
await manager.start_task(task.task_id)

# 查询状态
info = manager.get_task(task.task_id)
print(info.status, info.findings_count)

# 列出所有任务
tasks = manager.list_tasks()
stats = manager.get_stats()
```

## 输出文件

```
output/tasks/{task_id}/
  findings.json           # 结构化缺陷数据
  evidence_store.json     # v2 新增：共享证据仓库
  report.md               # Markdown 审查报告
  {id}_judge.json         # AI 评审六维评分
  {id}_judge.md           # 评审报告（Markdown）
  {id}_judge_input.json   # 给 AI Judge 的标准化输入（含 policy_references）
  {id}_judge_transcript.jsonl  # Judge 调用轨迹
  {id}_transcript.jsonl   # 完整智能体交互日志
```

## 配置说明
- `max_concurrent`：最大并行任务数（默认 3），超出通过 asyncio.Semaphore 排队
- `output_dir`：任务输出目录
- 状态变更时自动持久化至 `task_store.json`
