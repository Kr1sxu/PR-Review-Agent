# Judge 评估模块 — PR-Review Agent v2

AI 六维评分，独立于审查流程执行。

## 模块清单

| 文件 | 功能 |
|------|------|
| judge_runner.py | JudgeRunner：调用模型进行六维评分，输出 judge.json + judge.md |

## v2 变更

- `_build_prompt()` 现在读取 `policy_references`，注入到 Judge prompt 中
- Judge 可以参考企业规范评分，提升合规覆盖度评估准确性
- 输入来源优先从 EvidenceStore 构造（含完整上下文），降级时从 findings 构造

## 六维评分

| 维度 | 说明 |
|------|------|
| 关键风险覆盖 | 是否覆盖所有高危安全漏洞、数据泄露、支付风险 |
| 证据质量 | 每条缺陷是否附带充分、准确的代码证据 |
| 风险准确度 | 严重程度分级是否合理，是否存在过度告警或遗漏 |
| 噪声控制 | 是否存在重复或无效告警，去重和合并是否到位 |
| 可操作性 | 修复建议是否具体、可操作、可落地 |
| 报告清晰度 | 报告结构是否清晰，缺陷描述是否准确易懂 |

## 使用示例

```python
from src.judge.judge_runner import JudgeRunner

runner = JudgeRunner(model=mimo_model)

# 从 EvidenceStore 构造输入（v2 推荐）
judge_input = {
    "diff_summary": "...",
    "pr_description": "...",
    "findings": {...},
    "policy_references": [...],  # v2 新增
}

result = await runner.run(judge_input)
print(result.scores.total_score)  # 总分

# 保存结果
runner.save_result(result, "output/tasks/{task_id}", task_id)
```
