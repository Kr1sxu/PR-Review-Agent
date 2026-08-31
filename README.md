# PR-Review Agent v2.2

> 基于 AgentScope 的多智能体 PR 代码审查系统 — PostgreSQL + pgvector 存储 · 三层模型架构

## 系统架构（v2.2）

### 总体分层

```
Web 前端 (SPA)  /  命令行 CLI
        │
   FastAPI 后端
        │
   WebTaskManager（异步队列，最大 3 并发）
        │
   流程引擎（Simple / Council / Debate / Agentic）
        │
   ┌─────────────────────────────────────────────────────┐
   │         AgentFactory（三层模型分配）                  │
   │  强模型(DeepSeek) → Lead/Critic/Judge/ReportWriter  │
   │  中模型(GLM-5.2)  → company_policy_reviewer         │
   │  轻模型(MiMo)     → Reviewer x5                     │
   └─────────────────────────────────────────────────────┘
        │
   ┌─────────────────────────────────────────────────────┐
   │         共享证据仓库 EvidenceStore                    │
   │  findings + policy_references + challenges +        │
   │  decisions + debate_history                         │
   │  实时持久化 → PostgreSQL                             │
   └─────────────────────────────────────────────────────┘
        │
   工具集（read_file / search_code / run_tests / risk_scan / retrieve_company_policy）
        │
   RAG 知识库（安全 / 支付 / 测试规范）→ 向量 + BM25 双路召回 + RRF 融合
        │
   PostgreSQL + pgvector（审查数据 + 向量存储 + 长期记忆）
```

### Council 模式（委员会审查）

> 两轮裁决 + 一轮质疑：Lead Controller 初裁 → Critic 质疑 → Lead Controller 终裁

```
                    ┌──────────────────────────────────┐
                    │    Reviewer x5（并行审查）         │  ← 轻模型(MiMo)
                    │  security_expert / logic_reviewer │
                    │  test_engineer / maintainability  │
                    │  compliance_checker               │
                    │              +                    │
                    │  company_policy_reviewer（独立）   │  ← 中模型(GLM-5.2)
                    └───────────────┬──────────────────┘
                                    │ findings
                                    ▼
                    ┌──────────────────────────────────┐
                    │         EvidenceStore            │  → PostgreSQL 实时持久化
                    └───────────────┬──────────────────┘
                                    │
                                    ▼
                    ┌──────────────────────────────────┐
                    │    程序化合并（去重相似 findings）  │
                    └───────────────┬──────────────────┘
                                    │
                                    ▼
                    ┌──────────────────────────────────┐
                    │  Lead Controller（第一次裁决）     │  ← 强模型(DeepSeek)
                    │  ACCEPT / REJECT / DOWNGRADE      │
                    └───────────────┬──────────────────┘
                                    │ 裁决结果写入 EvidenceStore
                                    ▼
                    ┌──────────────────────────────────┐
                    │     Critic（一轮质疑验证）         │  ← 强模型(DeepSeek)
                    │  CHALLENGE / DOWNGRADE /          │
                    │  MERGE / REJECT                   │
                    │  （质疑结果写入 EvidenceStore）     │
                    └───────────────┬──────────────────┘
                                    │ 有质疑结果时
                                    ▼
                    ┌──────────────────────────────────┐
                    │  Lead Controller（最终确认）       │  ← 强模型(DeepSeek)
                    │  基于 Critic 质疑后的最新状态       │
                    │  做出终裁决定                      │
                    └───────────────┬──────────────────┘
                                    │
                                    ▼
                    ┌──────────────────────────────────┐
                    │    EvidenceStore 持久化到 PostgreSQL│
                    └───────────────┬──────────────────┘
                                    │
                                    ▼
                    ┌──────────────────────────────────┐
                    │  ReportWriterAgent 生成报告        │  ← 强模型(DeepSeek)
                    └───────────────┬──────────────────┘
                                    │
                                    ▼
                    ┌──────────────────────────────────┐
                    │  Judge 六维评分                    │  ← 强模型(DeepSeek)
                    │  （含 policy_references 权重）     │
                    └──────────────────────────────────┘
```

### Debate 模式（多轮辩论）

> 在 Council 基础上引入多轮动态博弈：Lead Controller 调度质疑 → 反驳 → 补证 → 合并 → 拒绝

```
   Reviewer x5 + company_policy_reviewer 并行审查
        │
        ▼
   EvidenceStore 收集 findings
        │
        ▼
   ┌─── 多轮循环（max_rounds）───────────────────────────┐
   │                                                      │
   │   Lead Controller 选择动作：                          │
   │     CHALLENGE → 调用原审查者反驳                      │
   │     REBUTTAL  → 原审查者补充证据                      │
   │     SUPPLEMENT → 工具补证（read_file/search_code）   │
   │     MERGE     → 合并重复 findings                    │
   │     REJECT    → 拒绝不成立的 finding                  │
   │     ACCEPT    → 接受，进入下一轮                      │
   │                                                      │
   │   每轮结果写入 EvidenceStore                          │
   │   共识分 (consensus_score) 递增                      │
   │                                                      │
   │   终止条件：共识分 ≥ 0.8 或达到最大轮次               │
   └──────────────────────────────────────────────────────┘
        │
        ▼
   ReportWriterAgent → Judge
```

## 快速开始

### 环境要求

- Python 3.11+
- Docker Desktop（用于 PostgreSQL + pgvector）
- 代理网络（首次拉取 Docker 镜像需要）

### 安装

```bash
# 1. 克隆仓库
git clone <repo-url>
cd "PR-Review Agent"

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 启动 PostgreSQL + pgvector（需要 Docker Desktop 运行）
docker compose up -d

# 4. 配置 API 密钥
copy .env.example .env
# 编辑 .env 填入你的 API Key
```

### 使用 CLI

```bash
# Debate 模式（默认，多轮辩论）
python -m src.main --repo ./demo/payment_repo --base HEAD~1 --target HEAD --mode debate

# Council 模式（委员会审查）
python -m src.main --repo ./demo/payment_repo --base HEAD~1 --target HEAD --mode council

# 指定最大辩论轮次
python -m src.main --repo ./demo/payment_repo --base a83add9 --target 78f934a --mode debate --max-rounds 3

# 禁用 RAG（离线模式）
python -m src.main --repo ./demo/payment_repo --base HEAD~1 --target HEAD --no-rag
```

### 使用 Web UI

```bash
python -m src.web_app
# 打开 http://127.0.0.1:8000
```

## 三层模型架构

系统根据不同角色的复杂度分配不同级别的模型，实现成本与能力的平衡：

| 层级 | 模型 | API | 分配角色 | 选型理由 |
|------|------|-----|----------|----------|
| **强模型** | DeepSeek V4 Flash | `api.deepseek.com` | Lead Controller、Critic、ReportWriter、Judge | 复杂推理、多轮裁决、报告生成 |
| **中等模型** | GLM-5.2 | `open.bigmodel.cn` | company_policy_reviewer | 工具调用、跨文件取证 |
| **轻量模型** | MiMo V2.5 Pro | `api.xiaomimimo.com` | Reviewer ×5 | 专项分析、并行扫描 |
| **向量模型** | text-embedding-v4 | 阿里云 MaaS | RAG 检索 | 1024维向量化 |

> 三个模型来自不同厂商，保证 Debate 模式下审查视角的多样性。

### 配置方式

`.env` 中配置三套 API：

```env
# 强模型
STRONG_API_URL=https://api.deepseek.com
STRONG_API_KEY=sk-xxx
STRONG_MODEL_NAME=deepseek-v4-flash

# 中等模型
MEDIUM_API_URL=https://open.bigmodel.cn/api/paas/v4
MEDIUM_API_KEY=xxx
MEDIUM_MODEL_NAME=glm-5.2

# 轻量模型
LIGHT_API_URL=https://api.xiaomimimo.com/v1
LIGHT_API_KEY=sk-xxx
LIGHT_MODEL_NAME=mimo-v2.5-pro
```

`config/settings.yaml` 中通过 `${STRONG_API_URL}` 等环境变量引用。

## PostgreSQL + pgvector 存储

### 为什么用 PostgreSQL

| 原方案 | 新方案 | 改进 |
|--------|--------|------|
| JSON 文件 | PostgreSQL | 并发安全、结构化查询、事务保障 |
| 内存 vector list | pgvector | 向量持久化、索引加速、跨任务检索 |
| 无长期记忆 | review_history + review_vectors | 跨任务相似审查检索、高频问题发现 |

### 数据库表结构

| 表名 | 用途 |
|------|------|
| `review_history` | 审查任务摘要（长期记忆） |
| `findings` | 审查发现的缺陷 |
| `policy_references` | 公司规范引用 |
| `challenges` | Critic 质疑记录 |
| `decisions` | Lead Controller 裁决记录 |
| `debate_history` | 辩论轮次记录 |
| `rag_vectors` | RAG 知识库向量（pgvector） |
| `review_vectors` | 历史审查向量（长期记忆检索） |

### Docker 配置

```yaml
# docker-compose.yml
services:
  db:
    image: pgvector/pgvector:pg16
    container_name: pr-review-db
    ports:
      - 5432:5432
    environment:
      POSTGRES_DB: pr_review
      POSTGRES_USER: pr_review
      POSTGRES_PASSWORD: pr_review_2026
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./scripts/init.sql:/docker-entrypoint-initdb.d/init.sql
```

## 输出产物

每次审查在 `output/tasks/{id}/` 下生成：

```
{id}/
  findings.json               # 结构化缺陷数据
  evidence_store.json         # 共享证据仓库
  report.md                   # Markdown 审查报告
  {id}_judge.json             # AI 评审六维评分
  {id}_judge.md               # 评审报告（Markdown）
  {id}_judge_input.json       # 给 AI Judge 的标准化输入
  {id}_judge_transcript.jsonl # Judge 调用轨迹
  {id}_transcript.jsonl       # 完整智能体交互日志
```

同时，所有数据实时写入 PostgreSQL，支持跨任务查询。

## 知识库

`knowledge_base/` 目录下存放企业编码规范：
- `security.md` — 安全编码规范
- `payment.md` — 支付业务规范
- `testing.md` — 测试规范

启用 RAG 后，系统自动将知识库切片存入 pgvector 并构建 BM25 倒排索引，检索时采用 **双路召回 + RRF 融合排序**。

### RAG 检索流程

```
Query → ┌─ 向量检索（pgvector 余弦相似度）── semantic ──┐
        │                                                ├→ RRF 融合 → Top-K
        └─ BM25 关键词检索（内存倒排索引）── keyword ────┘
```

- **向量检索**：语义匹配，能理解同义词和上下文
- **BM25 检索**：精确关键词匹配，对专有名词和代码术语更敏感
- **RRF 融合**：Reciprocal Rank Fusion，公式 `score(d) = Σ 1/(k + rank(d))`，k=60
- **降级策略**：向量不可用时 BM25 兜底，BM25 无结果时向量兜底


## 审查技能（Skill）

`skills/code-review/SKILL.md` 定义了系统化代码审查指南，自动注入到所有 Agent 的 prompt 中。

## company_policy_reviewer

独立于 Reviewer 组，使用中等模型（GLM-5.2），专门负责主动发现违反公司安全与支付规范的代码风险。

**专用工具：**
- `risk_scan` — 基于正则模式扫描代码中的风险
- `retrieve_company_policy` — 从知识库检索对应的公司策略条文

**输出：** 结构化 findings（含 policy_reference 字段），写入 EvidenceStore 供 Critic、Lead Controller 和 Judge 参考。

## 配置说明

所有配置通过 `config/settings.yaml` + `.env` 管理：

| 配置项 | 文件 | 说明 |
|--------|------|------|
| 三套模型 API 密钥 | `.env` | STRONG_* / MEDIUM_* / LIGHT_* / EMBEDDING_* |
| 数据库连接 | `.env` | DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD |
| 模型参数 | `settings.yaml` | `model.strong` / `model.medium` / `model.light` / `model.embedding` |
| 流程配置 | `settings.yaml` | `flow.default_mode` / `flow.rag_enabled` |
| RAG 配置 | `settings.yaml` | `rag.chunk_size` / `rag.top_k` / `rag.similarity_threshold` |
| 数据库配置 | `settings.yaml` | `database.*` |
| Prompt 模板 | `config/prompts/` | scanner / critic / lead_controller / report_writer / judge |

## 项目结构

```
PR-Review Agent/
├── config/
│   ├── prompts/              # Prompt 模板
│   └── settings.yaml         # 主配置文件
├── demo/                     # 11 个演示仓库（含故意缺陷）
│   ├── payment_repo/         # 支付服务
│   ├── user_auth_repo/       # 用户认证
│   ├── api_repo/             # API 服务
│   ├── order_service_repo/   # 订单服务
│   ├── billing_service_repo/ # 计费服务
│   ├── token_verify_repo/    # Token 验证
│   ├── notification_repo/    # 通知服务
│   ├── config_module_repo/   # 配置模块
│   ├── data_pipeline_repo/   # 数据管道
│   ├── task_scheduler_repo/  # 任务调度
│   └── webhook_repo/         # Webhook 服务
├── docker-compose.yml        # PostgreSQL + pgvector 容器
├── scripts/
│   └── init.sql              # 数据库初始化脚本（8 张表）
├── skills/
│   └── code-review/
│       └── SKILL.md          # 代码审查技能定义
├── knowledge_base/           # RAG 知识库（安全/支付/测试规范）
├── src/
│   ├── core/                 # 基础设施
│   │   ├── config_loader.py  # 配置加载（.env + yaml）
│   │   ├── database.py       # PostgreSQL 连接池（asyncpg）
│   │   ├── file_utils.py     # 文件工具
│   │   ├── logger.py         # 结构化日志
│   │   ├── serializer.py     # JSON 序列化
│   │   ├── skill_loader.py   # Skill 加载器
│   │   └── transcript_logger.py # 交互日志记录
│   ├── models/               # 模型封装
│   │   ├── mimo_wrapper.py   # ChatModel（OpenAI 兼容，支持三家 API）
│   │   ├── embedding.py      # EmbeddingModel（text-embedding-v4）
│   │   └── schemas.py        # Pydantic 输出 Schema
│   ├── agents/               # 智能体
│   │   ├── agent_factory.py  # AgentFactory（三层模型分配）
│   │   ├── reviewer_agent.py # Reviewer x5
│   │   ├── company_policy_reviewer.py
│   │   ├── critic_agent.py   # Critic
│   │   ├── lead_controller.py # Lead Controller
│   │   ├── report_writer.py  # ReportWriterAgent
│   │   └── judger_agent.py   # Judge
│   ├── tools/                # 工具集
│   │   ├── git_ops_tool.py   # Git 操作
│   │   ├── read_file.py      # 文件读取
│   │   ├── search_code.py    # 代码搜索
│   │   ├── run_tests.py      # 测试执行
│   │   ├── risk_scan.py      # 风险扫描
│   │   ├── retrieve_company_policy.py # 规范检索
│   │   └── tool_registry.py  # 工具注册
│   ├── flows/                # 流程引擎
│   │   ├── base_flow.py      # 基类
│   │   ├── simple_flow.py    # Simple 模式
│   │   ├── council_flow.py   # Council 模式
│   │   ├── debate_flow.py    # Debate 模式
│   │   ├── agentic_flow.py   # Agentic 模式
│   │   └── evidence_store.py # 共享证据仓库（PostgreSQL 持久化）
│   ├── rag/                  # RAG 知识检索
│   │   ├── chunker.py        # Markdown 切片
│   │   ├── vector_store.py   # pgvector 向量存储
│   │   └── retriever.py      # 检索器
│   ├── report/               # 报告生成
│   │   ├── findings.py       # FindingsCollection
│   │   └── report_renderer.py # 离线报告渲染
│   ├── judge/                # AI 评审
│   │   └── judge_runner.py   # 六维评分
│   ├── scheduler/            # 任务调度
│   │   └── task_manager.py   # WebTaskManager（异步队列）
│   ├── web/                  # Web API 路由
│   ├── main.py               # CLI 入口
│   └── web_app.py            # FastAPI 应用入口
├── frontend/                 # 原生 HTML/CSS/JS 前端
├── tests/                    # 测试套件
├── output/                   # 审查输出目录
├── .env                      # 环境变量（API 密钥、数据库密码）
├── .env.example              # 环境变量模板
├── requirements.txt          # Python 依赖
└── README.md
```

## 技术选型

| 组件 | 方案 | 选型理由 |
|------|------|----------|
| 智能体框架 | AgentScope v2 | 多智能体协作，原生工具/模型支持 |
| 生成模型 | DeepSeek + GLM + MiMo | 三层分级，不同厂商保证辩论多样性 |
| 向量模型 | text-embedding-v4 | 1024 维，支持中文语义 |
| 数据库 | PostgreSQL 16 + pgvector | 结构化存储 + 向量检索一体化 |
| 异步驱动 | asyncpg | 高性能异步 PostgreSQL 连接池 |
| Web 框架 | FastAPI | 异步支持，自动生成 API 文档 |
| 前端 | 原生 HTML/CSS/JS | 轻量，无需构建工具 |
| 容器 | Docker Compose | 一键部署 PostgreSQL + pgvector |
| 图表 | Chart.js | 六维评分可视化 |

## 修改记录

### v2（2026-07-30）
- 新增 Lead Controller Agent（动态裁决与调度）
- 新增 ReportWriterAgent（LLM 驱动报告生成）
- 新增 EvidenceStore（共享证据仓库，持久化到磁盘）
- company_policy_reviewer 从 Scanner 组独立
- Debater 改造为 Critic（移除 ACCEPT，新增补证建议）
- 删除 Merger Agent（由程序化去重替代）
- Council/Debate 流程重写（Lead Controller 驱动）
- Judge 支持读取 policy_references
- 新增 7 个测试文件，72 个测试用例

### v2.1（2026-08-12）— 工具调用与 Demo 改进
- **MiMo 工具调用支持**：修复 `mimo_wrapper.py` 中 `_call_api` 未传递 `tools` 和 `tool_choice` 参数的 bug
- **新增 5 个非自包含 Demo**：`token_verify_repo`、`order_service_repo`、`notification_repo`、`config_module_repo`、`billing_service_repo`
- **新增 Pydantic 输出 Schema**：`src/models/schemas.py` 定义 `FindingsOutput`
- **Reviewer 角色调整**：不使用工具，仅基于 diff 和 RAG 上下文分析
- **company_policy_reviewer 迭代防护**：`max_iters=5` 防止工具调用循环

### v2.2（2026-08-13）— PostgreSQL + pgvector 存储重构
- **存储层重写**：EvidenceStore 从 JSON 文件迁移到 PostgreSQL 实时持久化
- **向量存储迁移**：RAG 向量从内存 list 迁移到 pgvector 表
- **新增长期记忆**：`review_history` + `review_vectors` 支持跨任务检索
- **新增 Docker 依赖**：`docker-compose.yml` 部署 pgvector 容器
- **新增数据库模块**：`src/core/database.py`（asyncpg 连接池）
- **新增 8 张数据库表**：`scripts/init.sql` 初始化脚本
- **适配异步**：`retriever.py` 改用异步向量检索

### v2.3（2026-08-13）— 三层模型架构
- **模型分层**：强模型(DeepSeek) / 中等模型(GLM-5.2) / 轻量模型(MiMo)
- **不同厂商**：三个模型来自不同 API 提供商，保证 Debate 视角多样性
- **AgentFactory 改造**：新增 `strong_model` / `medium_model` / `light_model` 参数
- **TaskManager 改造**：创建三个模型实例传入 AgentFactory
- **向后兼容**：`AgentFactory(model=xxx)` 旧写法仍有效
- **配置扩展**：`.env` 和 `settings.yaml` 新增三套 API 配置

### v2.4（2026-08-14）— 混合检索：向量 + BM25 双路召回
- **新增 BM25Retriever**：`src/rag/bm25_retriever.py`，纯 Python 实现 BM25 算法（k1=1.5, b=0.75），中文 + 英文混合分词
- **RRF 融合排序**：`reciprocal_rank_fusion()` 函数，合并向量检索和 BM25 检索结果，k=60
- **Retriever 重写**：`src/rag/retriever.py` 改为双路并行召回 + RRF 融合，外部 API 不变
- **VectorStore 扩展**：新增 `get_all_chunks_async()` 从 PostgreSQL 加载全量 chunk 供 BM25 构建索引
- **三种降级模式**：`hybrid`（双路融合）→ `vector-only`（BM25 不可用）→ `bm25-only`（向量不可用）
- **无外部依赖**：BM25 算法纯 Python 实现，无需 `rank-bm25` 库