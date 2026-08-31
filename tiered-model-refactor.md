# 分层模型架构重构记录

> 日期：2026-08-13
> 变更类型：架构优化
> 影响范围：模型分配、Agent 创建、配置系统

---

## 一、重构背景

原系统所有 Agent 共用同一个 MiMo 模型 API，存在以下问题：

- 同质化：10 个 Agent 本质是同一模型加不同 prompt
- 成本浪费：5 个 Reviewer 并行 = 5 次完整 diff + RAG 上下文的 API 调用
- 能力错配：简单任务和复杂任务使用同一模型

---

## 二、分层模型策略

| 层级 | 模型 | 角色 | 说明 |
|---|---|---|---|
| 强模型 | MiMo Pro | Lead Controller、Critic、ReportWriter、Judge | 复杂推理 |
| 中等模型 | MiMo Medium | company_policy_reviewer | 工具调用、跨文件取证 |
| 轻量模型 | MiMo Lite | Reviewer x5 | 专项分析 |
| 向量模型 | text-embedding-v4 | RAG 检索 | 向量化（已有） |

当前暂时使用同一份 MiMo API key，后续替换为 Lite 版本即可生效。

---

## 三、修改文件

### 3.1 AgentFactory
文件：src/agents/agent_factory.py
改动：新增 strong_model / light_model 参数，按角色分配模型
向后兼容：旧写法 AgentFactory(model=...) 仍然有效

### 3.2 TaskManager
文件：src/scheduler/task_manager.py
改动：创建两个模型实例传入 AgentFactory

### 3.3 配置文件
文件：.env / config/settings.yaml
新增：MIMO_LITE_API_URL / MIMO_LITE_API_KEY / MIMO_LITE_MODEL_NAME

---

## 四、未修改的文件（向后兼容）

council_flow.py / debate_flow.py / reviewer_agent.py / critic_agent.py
lead_controller.py / report_writer.py / judger_agent.py / test_agents.py
以上文件均不需要修改，只调 factory.create_xxx() 不感知模型分配。

---

## 五、后续替换轻量模型

获得 MiMo Lite API 后，只需修改 .env 中的 MIMO_LITE_* 变量，无需改代码。

---

## 六、成本优化预估

| 场景 | 原方案 | 分层后 |
|---|---|---|
| Reviewer x5 并行 | 5 次 Pro | 5 次 Lite（降低约60%） |
| Lead Controller | 1 次 Pro | 1 次 Pro（不变） |
| Critic | 1 次 Pro | 1 次 Pro（不变） |
| 单次审查总计 | 7 次 Pro | 2 Pro + 1 Medium + 4 Lite |