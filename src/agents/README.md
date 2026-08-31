# 智能体模块 — PR-Review Agent v2.1

基于 AgentScope v2 构建的多角色智能体系统。

## 智能体清单

| 角色 | 文件 | 说明 |
|------|------|------|
| Reviewer（×5） | reviewer_agent.py | security_expert、logic_reviewer、test_engineer、maintainability_reviewer、compliance_checker |
| company_policy_reviewer | company_policy_reviewer.py | 独立文件：风险扫描 + 政策检索，写入 EvidenceStore |
| Critic | critic_agent.py | 质疑证据与严重级别（原 Debater） |
| Lead Controller | lead_controller.py | v2 新增：动态裁决与调度 |
| ReportWriterAgent | report_writer.py | v2 新增：LLM 驱动报告生成 |
| Judge | judger_agent.py | 六维评分（不变） |

## AgentFactory 工厂类

调用示例：

```python
from src.models.mimo_wrapper import create_mimo_model
from src.agents.agent_factory import AgentFactory

model = create_mimo_model(api_url="...", api_key="...", model_name="mimo")
factory = AgentFactory(model=model, allowed_roots=["/path/to/repo"])

# 创建所有智能体
agents = factory.create_all(rag_context="企业规范内容...")
reviewers = agents["reviewers"]  # 包含 5 个 reviewer 的字典
company_policy = agents["company_policy_reviewer"]
critic = agents["critic"]
lead = agents["lead_controller"]
writer = agents["report_writer"]
judge = agents["judge"]

# 或单独创建
reviewers = factory.create_reviewers(roles=["security_expert"])
critic = factory.create_critic()
```

## 设计说明
- 所有智能体继承 AgentScope 的 `Agent` 基类
- 系统提示词定义各角色专属的审查重点
- 可用时将 RAG 上下文注入 Reviewer 提示词
- 工厂类自动处理在线/离线模型选择
- company_policy_reviewer 独立文件，使用专用工具 risk_scan + retrieve_company_policy
- 向后兼容：SCANNER_ROLES、create_scanner_agent、create_scanners 作为别名保留
