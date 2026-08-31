# PR-Review Agent 项目学习文档（v2.3）

> 本文档用于系统性学习 PR-Review Agent 项目的架构设计、模块逻辑和代码编写思路。
> 最后更新：v2.3 — PostgreSQL + pgvector 存储重构、三层模型架构（DeepSeek / GLM / MiMo）。

---

## 目录

1. [项目目的与背景](#1-项目目的与背景)
2. [技术选型](#2-技术选型)
3. [整体架构](#3-整体架构)
4. [目录结构详解](#4-目录结构详解)
5. [配置系统](#5-配置系统)
6. [核心基础层 (src/core)](#6-核心基础层-srccore)
7. [模型封装层 (src/models)](#7-模型封装层-srcmodels)
8. [智能体层 (src/agents)](#8-智能体层-srcagents)
9. [工具层 (src/tools)](#9-工具层-srctools)
10. [流程引擎层 (src/flows)](#10-流程引擎层-srcflows)
11. [EvidenceStore 数据中枢](#11-evidencetore-数据中枢)
12. [RAG 知识检索层 (src/rag)](#12-rag-知识检索层-srcrag)
13. [报告层 (src/report)](#13-报告层-srcreport)
14. [评审打分层 (src/judge)](#14-评审打分层-srcjudge)
15. [任务调度层 (src/scheduler)](#15-任务调度层-srcscheduler)
16. [Web 服务层 (src/web + src/web_app.py)](#16-web-服务层-srcweb--srcweb_apppy)
17. [前端界面 (frontend)](#17-前端界面-frontend)
18. [入口文件](#18-入口文件)
19. [数据流转全景](#19-数据流转全景)
20. [演示仓库 (demo)](#20-演示仓库-demo)
21. [测试策略 (tests)](#21-测试策略-tests)
22. [关键设计思想总结](#22-关键设计思想总结)

---

## 1. 项目目的与背景

### 1.1 解决什么问题

传统代码审查（Code Review）存在以下痛点：

- **重复告警**：多个审查者可能从不同角度报告同一个问题，导致重复
- **证据缺失**：审查意见缺乏代码证据支撑，开发者难以理解
- **风险等级不一致**：不同审查者对同一问题的风险评级可能差异很大
- **难以对标企业规范**：人工审查难以全面覆盖企业编码规范
- **缺乏裁决机制**：多角色意见冲突时，没有统一的仲裁流程

### 1.2 解决方案（v2.1）

PR-Review Agent v2 采用 **Lead Controller 调度的多角色协作** 架构：

1. **Reviewer x5**（5 个专业审查智能体）从不同角度并行扫描代码
2. **company_policy_reviewer**（独立智能体）基于企业私有规范主动发现问题
3. **Critic**（质疑专家）对所有 findings 进行证据质疑和严重级别校准
4. **Lead Controller**（裁决调度器）动态裁决每条 finding 的最终去留
5. **ReportWriterAgent** 生成标准化审查报告
6. **Judge** 对报告进行六维评分
7. **EvidenceStore** 作为数据中枢，持久化所有中间结果

### 1.3 核心价值

- 多角色分工自动扫描，替代初级人工审核
- Lead Controller 裁决机制降低误报率，保证审查质量
- EvidenceStore 持久化所有证据，支持复盘和审计
- 本地 RAG 绑定企业规范，每条缺陷附带规范原文依据
- 全流程可视化，支持 Web 界面和 CLI 两种入口

---

## 2. 技术选型

| 组件 | 方案 | 选型理由 |
|------|------|----------|
| 智能体框架 | AgentScope v2 | 多智能体协作，原生工具/模型支持 |
| 强模型 | DeepSeek V4 Flash | 复杂推理、多轮裁决、报告生成 |
| 中等模型 | GLM-5.2（智谱） | 工具调用、跨文件取证 |
| 轻量模型 | MiMo V2.5 Pro | 专项分析、并行扫描 |
| 向量模型 | text-embedding-v4 | 1024 维向量化，支持中文语义 |
| 数据库 | PostgreSQL 16 + pgvector | 结构化存储 + 向量检索一体化 |
| 异步驱动 | asyncpg | 高性能异步 PostgreSQL 连接池 |
| Web 框架 | FastAPI | 异步支持，自动生成 API 文档 |
| 前端 | 原生 HTML/CSS/JS | 轻量，无需构建工具 |
| 容器 | Docker Compose | 一键部署 PostgreSQL + pgvector |
| 图表 | Chart.js | 六维评分可视化 |

---

## 3. 整体架构

### 3.1 五层架构

```
┌─────────────────────────────────────────────────┐
│           第一层：交互接入层                       │
│        Web 前端 (SPA)  /  CLI 命令行             │
├─────────────────────────────────────────────────┤
│           第二层：任务调度层                       │
│     FastAPI 后端 + WebTaskManager 异步队列       │
├─────────────────────────────────────────────────┤
│           第三层：智能体业务层                     │
│  Reviewer x5 + company_policy_reviewer          │
│  → EvidenceStore → Critic → Lead Controller     │
│  → ReportWriterAgent → Judge                    │
│  Flows (Simple/Council/Debate/Agentic)          │
│  RAG 知识检索  │  EvidenceStore 持久化           │
├─────────────────────────────────────────────────┤
│           第四层：底层支撑层                       │
│  Git 操作 │ 文件 IO │ 序列化 │ 日志 │ 模型网络    │
├─────────────────────────────────────────────────┤
│           第五层：环境支撑层                       │
│    配置读取 (.env + settings.yaml) │ 测试        │
└─────────────────────────────────────────────────┘
```

### 3.2 v2.1 角色体系（10 个 Agent）

```
Reviewer x5（reviewer_agent.py，一个文件定义 5 个角色）
  ├── security_expert       安全专家
  ├── logic_reviewer        逻辑审查员
  ├── test_engineer         测试工程师
  ├── maintainability_reviewer  可维护性检查员
  └── compliance_checker    规范检查员

company_policy_reviewer（company_policy_reviewer.py，独立文件）
  └── 使用 risk_scan + retrieve_company_policy，写入 EvidenceStore

Critic（critic_agent.py，原 Debater，v2 改造）
  └── 质疑证据、校准严重级别、建议补证文件

Lead Controller（lead_controller.py，v2 新增）
  ├── Council 模式：一次性裁决所有 findings
  └── Debate 模式：多轮动态调度（CHALLENGE/REBUTTAL/SUPPLEMENT/MERGE/ACCEPT/REJECT/FINISH）

ReportWriterAgent（report_writer.py，v2 新增）
  └── LLM 驱动报告生成，离线时降级为 fallback_render()

Judge（judger_agent.py，保留不变）
  └── 六维评分（覆盖/证据/准确/噪音/可执行/清晰）
```

### 3.3 数据中枢：EvidenceStore

所有角色通过 `EvidenceStore`（`src/flows/evidence_store.py`）共享数据：

```
Reviewer x5 ─┐
              ├──→ EvidenceStore ←── Critic（质疑/补证）
company_policy ─┘       │
                        ├──→ Lead Controller（读取 findings + 裁决）
                        ├──→ ReportWriterAgent（生成报告）
                        ├──→ Judge（评分）
                        └──→ 持久化到 output/tasks/{task_id}/evidence_store.json
```

---

## 4. 目录结构详解

```
PR-Review Agent/
├── src/
│   ├── core/                    # 底层支撑
│   │   ├── config_loader.py     # 配置加载（单例）
│   │   ├── logger.py            # 日志系统（JSONL 转录）
│   │   ├── git_ops.py           # Git 只读操作
│   │   ├── file_utils.py        # 文件工具（路径白名单）
│   │   ├── serializer.py        # JSON 序列化
│   │   ├── skill_loader.py      # SKILL.md 加载
│   │   └── task_manager.py      # 任务状态管理
│   │
│   ├── models/                  # 模型封装
│   │   ├── mimo_wrapper.py      # MiMo 聊天模型
│   │   └── embedding.py         # 向量模型
│   │
│   ├── agents/                  # 智能体层（v2.1）
│   │   ├── reviewer_agent.py    # Reviewer x5（原 scanner_agent.py）
│   │   ├── company_policy_reviewer.py  # 公司策略审查（独立文件）
│   │   ├── critic_agent.py      # Critic 质疑专家（原 debater_agent.py）
│   │   ├── lead_controller.py   # Lead Controller 裁决调度（v2 新增）
│   │   ├── report_writer.py     # ReportWriterAgent（v2 新增）
│   │   ├── judger_agent.py      # Judge 六维评分
│   │   └── agent_factory.py     # 统一工厂
│   │
│   ├── tools/                   # 工具层
│   │   ├── tool_registry.py     # 工具注册器
│   │   ├── read_file.py         # 只读文件读取
│   │   ├── search_code.py       # 代码搜索
│   │   └── run_tests.py         # 测试执行（默认禁用）
│   │
│   ├── flows/                   # 流程引擎层
│   │   ├── base_flow.py         # 流程基类
│   │   ├── simple_flow.py       # 规则静态分析（离线降级）
│   │   ├── council_flow.py      # Council 流程（v2）
│   │   ├── debate_flow.py       # Debate 流程（v2）
│   │   ├── agentic_flow.py      # Agentic 流程
│   │   └── evidence_store.py    # EvidenceStore 数据中枢（v2 新增）
│   │
│   ├── rag/                     # RAG 知识检索
│   │   ├── chunker.py           # 文档切片
│   │   ├── vector_store.py      # 向量存储
│   │   └── retriever.py         # 检索器
│   │
│   ├── report/                  # 报告层（v1 兼容）
│   │   ├── findings.py          # 缺陷数据结构
│   │   └── report_renderer.py   # 报告渲染器（离线降级用）
│   │
│   ├── judge/                   # 评审打分层
│   │   └── judge_runner.py      # 评分运行器
│   │
│   ├── web/                     # Web 服务
│   │   └── routes.py            # API 路由
│   │
│   └── web_app.py               # FastAPI 应用入口
│
├── config/
│   ├── settings.yaml            # 主配置
│   └── prompts/                 # Prompt 模板
│
├── frontend/                    # 前端 SPA
├── demo/                        # 演示仓库
├── output/                      # 运行输出
│   └── tasks/{task_id}/
│       ├── evidence_store.json  # EvidenceStore 持久化
│       ├── report.md            # 审查报告
│       └── judge.json           # 评分结果
│
├── tests/                       # 测试
├── Planv2.md                    # v2 改造计划（78 项）
├── learn.md                     # 本文档
└── README.md                    # 项目说明
```

---

## 5. 配置系统

### 5.1 双层配置模型

配置分为两层，职责分离：

- **.env**：存放敏感凭证（API 密钥、接口地址），不入库
- **config/settings.yaml**：存放业务参数（模型参数、智能体配置、RAG 参数等），使用 `${VAR_NAME}` 语法引用环境变量

### 5.2 ConfigLoader 实现逻辑 (src/core/config_loader.py)

```
设计模式：单例模式（__new__ 控制只创建一次实例）

加载流程：
1. 定位项目根目录（默认为 src/ 的上两级）
2. 加载 .env 文件到 os.environ（python-dotenv）
3. 读取 settings.yaml 原始内容
4. 正则替换 ${VAR_NAME} 为环境变量值
5. YAML 安全解析为字典
6. 检测离线模式（MIMO_API_KEY 或 MIMO_API_URL 缺失 → 离线）

核心方法：
- get(dotpath)    : 点分路径访问，如 "model.mimo.temperature"
- offline_mode    : 是否处于离线模式
- reload()        : 重新加载配置
- get_xxx_config(): 各模块的便捷访问方法
```

**学习要点**：正则替换环境变量 `${(\w+)}` 让 YAML 配置可以安全引用敏感值，避免将密钥硬编码在配置文件中。

---

## 6. 核心基础层 (src/core)

### 6.1 日志系统 (logger.py)

```
类：TranscriptLogger

设计目标：每个任务独立日志 + 结构化 JSONL 转录

功能：
- 双通道输出：文件日志（DEBUG 级别）+ 控制台（INFO 级别）
- JSONL 转录：每条日志同时写入 {task_id}_transcript.jsonl
  格式：{"timestamp", "task_id", "level", "source", "message", "metadata"}
- 自定义日志级别：AGENT_ACTION (25)，用于记录智能体行为

日志级别层次：
  DEBUG(10) → INFO(20) → AGENT_ACTION(25) → WARNING(30) → ERROR(40)

全局管理：
- get_logger(task_id)  : 获取/创建任务级日志器（缓存在 _loggers 字典中）
- clear_loggers()      : 清理所有日志器
```

**学习要点**：JSONL 格式（每行一个 JSON 对象）适合流式追加和后续检索，前端可通过 `/api/tasks/{id}/transcript` 接口按关键词过滤日志。

### 6.2 Git 操作 (git_ops.py)

```
类：GitOps

设计原则：只读操作，禁止任何写入

封装的 Git 命令：
- get_diff(base, target)         → git diff base target
- get_file_content(commit, file) → git show commit:file
- list_changed_files(base, target) → git diff --name-only
- get_commit_message(commit)     → git log -1 --format=%s
- get_commit_hash(ref)           → git rev-parse ref
- is_valid_ref(ref)              → 验证引用是否有效

异常体系：
  GitOpsError (基类)
    ├── RepoNotFoundError    : 路径不是 Git 仓库
    └── CommitNotFoundError  : 无效的 commit/分支引用

安全措施：
- subprocess 30 秒超时
- 捕获 stderr 区分不同错误类型
```

**学习要点**：通过 subprocess 调用 git 命令行而非 GitPython 的高级 API，保持了对 Git 操作的完全控制，且只读设计保证安全。

### 6.3 文件工具 (file_utils.py)

```
类：FileUtils

安全机制：路径白名单验证
- _validate_path(): 解析真实路径，检查是否在 allowed_roots 内
- PathViolationError: 路径越界时抛出

功能：
- read_file()     : 读取文件内容
- file_exists()   : 检查文件存在性
- list_dir()      : 目录遍历（支持 glob 模式）
- write_file()    : 写入文件（自动创建父目录）
- write_json()    : JSON 序列化后写入
```

### 6.4 序列化器 (serializer.py)

```
功能：处理 Python 特殊类型的 JSON 序列化

支持类型：
- datetime / date → {"__type__": "datetime", "value": "ISO格式"}
- Path            → {"__type__": "Path", "value": "路径字符串"}
- 自定义对象       → {"__type__": "类名", "value": {属性字典}}

核心函数：
- to_json(obj)     : 序列化
- from_json(str)   : 反序列化（通过 object_hook 还原类型）
- save_json()      : 保存到文件
- load_json()      : 从文件加载
- to_jsonl()       : 多条记录转 JSONL
- from_jsonl()     : JSONL 解析为列表
```

---

## 7. 模型封装层 (src/models)

### 7.1 MiMo 聊天模型 (mimo_wrapper.py)

```
类：MiMoChatModel (继承 AgentScope ChatModelBase)

核心设计：
- 兼容 OpenAI Chat Completions API 格式
- 异步 HTTP 调用（httpx.AsyncClient）
- 超时重试机制（可配置重试次数和间隔）
- 离线降级：缺少 API 密钥时返回 mock 响应

构造参数：
  credential  : OpenAICredential (api_key + base_url)
  model       : 模型名称
  parameters  : MiMoParameters (max_tokens, temperature, top_p)
  timeout     : HTTP 超时秒数
  max_retries : 重试次数

API 调用流程 (_call_api)：
  1. 检查离线模式 → 返回 mock 响应
  2. 格式化消息列表（_format_messages）
  3. 构建 payload (model, messages, max_tokens, temperature)
  4. httpx.AsyncClient POST 请求
  5. 解析响应 → ChatResponse（含 reasoning_content 字段）

离线模式判断 (is_offline)：
  - API URL 为空 → 离线
  - API Key 为空 → 离线
  - 否则返回提示文字

JSON 提取 (extract_json)：
  尝试顺序：
  1. 直接 json.loads(text)
  2. 正则匹配 ```json ... ``` 代码块
  3. 正则匹配 {...} 或 [...] 对象/数组
  4. 全部失败返回 None

工厂函数：create_mimo_model(...)
  简化创建流程，一行代码生成模型实例
```

**学习要点**：extract_json 的多层降级策略非常重要——大模型的输出格式不稳定，需要多种解析策略兜底。reasoning_content 字段的处理体现了对 MiMo 模型特性的适配。

### 7.2 向量模型 (embedding.py)

```
类：MiMoEmbeddingModel (继承 AgentScope EmbeddingModelBase)

设计特点：
- 独立 HTTP 调用，不依赖 OpenAI SDK
- 批量分片处理（默认 batch_size=16）
- 超时重试
- 离线降级返回零向量
- 内置余弦相似度计算

核心方法：
- _call_api(inputs)    : 异步调用 embedding API
- embed_single(text)   : 单文本向量化
- embed_batch(texts)   : 批量向量化（自动分片）
- similarity(a, b)     : 余弦相似度

离线处理：
  全部返回 [0.0] * dimensions（零向量），不会阻塞流程
```

---

## 8. 智能体层 (src/agents)

### 8.1 AgentFactory (agent_factory.py)

```
类：AgentFactory

职责：统一创建和管理所有智能体实例

构造：
  model       : ChatModelBase 实例（MiMo 或离线 mock）
  toolkit     : AgentScope Toolkit（工具集）
  skill_path  : SKILL.md 路径（注入审查指导）
  enable_tests: 是否启用测试执行工具
  allowed_roots: 文件工具允许的根目录

创建方法：
  create_reviewers(roles, rag_context)        → dict[str, Agent]  （5 个 Reviewer）
  create_company_policy_reviewer(rag_context)  → Agent
  create_critic()                              → Agent
  create_lead_controller()                     → Agent
  create_report_writer()                       → Agent
  create_judge()                               → Agent
  create_all(rag_context)                      → dict（一次性创建全部）

向后兼容：
  create_scanners() = create_reviewers()  （别名）
```

**学习要点**：工厂模式将智能体创建逻辑集中管理，调用方只需指定角色和配置，不关心具体的 Prompt 拼接和工具绑定细节。

### 8.2 Reviewer Agent (reviewer_agent.py)

```
文件：src/agents/reviewer_agent.py（v2.1 由 scanner_agent.py 重命名）

5 个专业角色，各自有独立的系统提示词：

1. security_expert (安全专家)
   关注：SQL注入、XSS、CSRF、敏感数据泄露、硬编码密钥、不安全反序列化

2. logic_reviewer (逻辑审查员)
   关注：空指针、边界条件、竞态条件、错误处理缺失、资源泄漏

3. test_engineer (测试工程师)
   关注：缺失测试、断言薄弱、测试隔离问题、边界测试缺失

4. maintainability_reviewer (可维护性审查员)
   关注：代码重复、复杂度过高、命名不规范、违反 SOLID 原则

5. compliance_checker (规范检查员)
   关注：编码规范、命名约定、文档要求、API 设计准则
   特殊：可引用 RAG 知识库中的企业规范

数据结构：
  REVIEWER_ROLES : dict  （5 个角色定义）
  SCANNER_ROLES  : REVIEWER_ROLES 的向后兼容别名

创建函数：
  create_reviewer_agent(role, model, toolkit, rag_context, skill_context) → Agent
  create_scanner_agent = create_reviewer_agent  （向后兼容别名）

创建逻辑：
  1. 查找角色定义（REVIEWER_ROLES[role]）
  2. 注入 skill 审查清单和反模式示例（如果有 SKILL.md）
  3. 注入 RAG 企业规范上下文（如果有）
  4. 加载输出 schema（优先从 skill 获取，否则使用默认格式）
  5. 创建 AgentScope Agent 实例，绑定模型和工具

输出格式：JSON 数组，每个缺陷包含
  id / category / severity / title / description /
  file_path / line_range / evidence / suggestion / confidence
```

### 8.3 Company Policy Reviewer (company_policy_reviewer.py)

```
文件：src/agents/company_policy_reviewer.py（v2.1 从 scanner_agent.py 独立）

定位：基于企业私有规范的主动审查角色
工具：risk_scan + retrieve_company_policy

工作流程：
  第一步：使用 risk_scan 对代码变更进行全面风险扫描
  第二步：对每个风险点，使用 retrieve_company_policy 获取公司规范
  第三步：结合风险模式和公司策略，生成结构化发现（含 policy_reference）

重点关注场景：
  - SQL 参数化（禁止字符串拼接）
  - Webhook 签名验证
  - 敏感信息日志泄露
  - 支付 fail-closed（异常不得静默吞掉）
  - 关键路径测试缺失
  - 支付/订单幂等性

输出：JSON 数组，每个缺陷包含 policy_reference 字段

创建函数：
  create_company_policy_reviewer(model, toolkit, rag_context, skill_context) → Agent

与其他 Reviewer 的区别：
  - 其他 Reviewer 使用通用 prompt + RAG 注入
  - company_policy_reviewer 使用专用工具（risk_scan + retrieve_company_policy）主动检索
  - 输出额外包含 policy_reference 字段，供 Critic/Lead/Judge 引用
```

### 8.4 Critic Agent (critic_agent.py)

```
文件：src/agents/critic_agent.py（v2 由 debater_agent.py 改造并替代）

定位：质疑验证专家，不做最终裁决（裁决由 Lead Controller 负责）

质疑操作类型（每条缺陷可选择）：
  - CHALLENGE  : 需要更多证据或存在错误（附带 suggest_files 补证建议）
  - DOWNGRADE  : 严重程度被高估，建议新的级别
  - MERGE      : 与其他缺陷重复，指定目标 ID
  - REJECT     : 缺陷无效（误报）

注意：v2 移除了 ACCEPT 动作，ACCEPT 由 Lead Controller 决定

补证建议（suggest_files）：
  当选择 CHALLENGE 时，Critic 会指出：
  - 需要查看哪些文件来验证此缺陷
  - 需要运行什么测试来确认
  - 还需要什么上下文信息

输出：
  - actions[]        : 每条缺陷的操作指令（含 suggest_files）
  - new_findings[]   : 新发现的缺陷
  - consensus_score  : 共识度 (0-1)，>=0.8 表示达成共识
  - summary          : 本轮质疑总结
```

### 8.5 Lead Controller (lead_controller.py)

```
文件：src/agents/lead_controller.py（v2 新增）

定位：动态裁决与调度器，是整个审查流程的核心决策者

Council 模式（一次性裁决）：
  读取所有 Reviewer + Critic 的 findings，一次性裁决每条 finding 的去留
  裁决动作：ACCEPT / REJECT / DOWNGRADE

Debate 模式（多轮动态调度）：
  Lead Controller 在每轮 Debate 中决定下一步动作：
  - CHALLENGE  : 要求 Reviewer 补充证据
  - REBUTTAL   : 要求 Reviewer 反驳 Critic 的质疑
  - SUPPLEMENT : 要求补充查看指定文件
  - MERGE      : 合并相似 findings
  - ACCEPT     : 接受某条 finding
  - REJECT     : 拒绝某条 finding
  - FINISH     : 结束辩论，进入报告阶段

解析函数：
  parse_lead_controller_output(raw_text) → dict
  validate_council_decision(decision) → bool
```

### 8.6 ReportWriterAgent (report_writer.py)

```
文件：src/agents/report_writer.py（v2 新增）

定位：LLM 驱动的报告生成器

功能：
  - 读取 EvidenceStore 中的所有 findings、decisions、policy_references
  - 调用 LLM 生成结构化 Markdown 报告
  - 报告包含：摘要、各 finding 详情、政策引用、评分建议

降级策略：
  - LLM 不可用时，使用 fallback_render() 程序化生成报告
  - fallback_render() 保证始终能输出有效报告

函数：
  create_report_writer_agent(model) → Agent
  generate_report(agent, evidence_store, pr_description) → str
  fallback_render(evidence_store) → str
```

### 8.7 Judge Agent (judger_agent.py)

```
文件：src/agents/judger_agent.py（保留不变）

职责：对审查报告进行六维标准化评分

六维评分体系（每项 0-100 分）：
  1. 关键风险覆盖 (critical_risk_coverage) - 是否覆盖所有高危问题
  2. 证据质量 (evidence_quality)         - 证据是否充分准确
  3. 风险准确度 (risk_accuracy)           - 严重程度分级是否合理
  4. 噪声控制 (noise_control)            - 是否有重复/无效告警
  5. 可操作性 (actionability)             - 修复建议是否具体可行
  6. 报告清晰度 (report_clarity)          - 报告结构是否清晰

输出：JSON 对象，包含 scores + evaluation (strengths/weaknesses/suggestions)
```

---

## 9. 工具层 (src/tools)

工具层为 AgentScope 智能体提供可调用的外部能力，全部注册到 Toolkit 中。

### 9.1 工具注册器 (tool_registry.py)

```
函数：create_toolkit(allowed_roots, enable_tests, test_commands)

创建 3 个工具实例并注册到 AgentScope Toolkit：
  1. ReadFileTool   - 只读文件读取
  2. SearchCodeTool - 代码搜索
  3. RunTestsTool   - 测试执行（默认禁用）
```

### 9.2 ReadFileTool (read_file.py)

```
类：ReadFileTool (继承 AgentScope ToolBase)

功能：读取文件内容并附带行号

安全设计：
  - is_read_only = True（标记为只读）
  - is_concurrency_safe = True（支持并发调用）
  - 路径白名单验证（allowed_roots）
  - 权限检查：始终返回 ALLOW

输出格式：
  "   1 | 第一行内容"
  "   2 | 第二行内容"
```

### 9.3 SearchCodeTool (search_code.py)

```
类：SearchCodeTool (继承 AgentScope ToolBase)

功能：关键词/正则表达式搜索代码

参数：
  keyword      : 搜索关键词或正则
  directory    : 搜索目录（默认 "."）
  file_pattern : 文件扩展名过滤（如 ".py"）
  max_results  : 最大结果数（默认 50）

实现：
  - 优先尝试正则编译，失败则转义为字面量
  - os.walk 递归遍历，跳过 .git/__pycache__/node_modules 等
  - 返回格式：relative_path:line_number: content
```

### 9.4 RunTestsTool (run_tests.py)

```
类：RunTestsTool (继承 AgentScope ToolBase)

功能：执行测试命令

安全设计（最重要）：
  - 默认禁用（enabled=False）
  - is_read_only = False（标记为非只读）
  - is_concurrency_safe = False（不支持并发）
  - 权限检查：禁用时返回 DENY
  - 命令白名单验证（allowed_commands）
  - 输出截断（stdout 最多 3000 字符，stderr 最多 2000 字符）
  - 超时控制（默认 60 秒）
```

**学习要点**：工具层的安全设计非常严格——所有工具默认只读，写操作（run_tests）默认禁用且需要显式启用。这是防止 AI 智能体意外修改代码的关键防线。

---

## 10. 流程引擎层 (src/flows)

流程引擎是系统的核心编排层，定义了不同审查模式下智能体的协作方式。

### 10.1 基类 (base_flow.py)

```
数据结构：

Finding (缺陷发现)：
  id, category, severity, title, description, file_path,
  line_range, evidence, suggestion, confidence, spec_reference, sources, metadata

ReviewResult (审查结果)：
  flow_mode, findings[], summary, duration_seconds, offline, metadata
  方法：to_dict() 序列化

BaseFlow (流程基类，抽象类)：
  属性：flow_mode → 流程标识符（从类名自动推导）
  
  execute(diff, pr_description, config) → ReviewResult：
    公开方法，负责计时和错误处理
    
  run(diff, pr_description, config) → ReviewResult：
    抽象方法，子类实现具体逻辑
```

**学习要点**：模板方法模式——execute() 提供统一的计时和异常处理框架，子类只需实现 run() 的核心逻辑。

### 10.2 SimpleFlow (simple_flow.py)

```
定位：基于规则的静态分析，无需模型调用，用于离线降级

工作流程：
  1. 解析 diff 为 {file_path: diff_segment} 字典
  2. 对每个文件应用正则模式匹配
  3. 安全模式 (SECURITY_PATTERNS)：9 个规则
     - 硬编码密码/API Key/Secret
     - SQL 注入风险（字符串拼接查询）
     - eval()/exec() 危险调用
     - innerHTML XSS 风险
     - shell=True 注入风险
     - SSL 验证禁用
  4. 质量模式 (QUALITY_PATTERNS)：7 个规则
     - TODO/FIXME/HACK 注释
     - 敏感关键词
     - 裸 except/broad except
     - 空 pass 语句
     - print/console.log 调试语句

性能目标：100 行 diff ≤ 10 秒

输出：offline=True 标记
```

### 10.3 CouncilFlow (council_flow.py) — v2

```
定位：委员会裁决流程（Lead Controller 一次性裁决）

工作流程：
  1. 创建 Reviewer x5 + company_policy_reviewer
  2. 并行执行所有 Reviewer（asyncio.gather）
  3. company_policy_reviewer 独立审查（使用专用工具）
  4. 所有 findings 写入 EvidenceStore
  5. 程序化合并（_programmatic_merge）去重相似 findings
  6. 创建 Lead Controller
  7. Lead Controller 一次性裁决所有 findings（ACCEPT/REJECT/DOWNGRADE）
  8. 裁决结果写入 EvidenceStore
  9. ReportWriterAgent 生成标准化报告
  10. 返回 ReviewResult

关键实现细节：
  - Reviewer 并行执行：asyncio.gather 并发调用
  - 程序化合并替代原 Merger Agent（删除了 Merger）
  - EvidenceStore 持久化到 output/tasks/{task_id}/evidence_store.json
  - 降级处理：ReportWriterAgent 不可用时使用 fallback_render()
```

### 10.4 DebateFlow (debate_flow.py) — v2

```
定位：辩论式审查流程（Lead Controller 多轮动态调度）

工作流程：
  1. 复用 CouncilFlow 的 Reviewer 并行扫描 + company_policy_reviewer
  2. 所有 findings 写入 EvidenceStore
  3. 程序化合并去重
  4. 进入辩论循环（最多 max_rounds 轮）：
     a. Critic 质疑当前 findings（CHALLENGE/DOWNGRADE/MERGE/REJECT）
     b. Lead Controller 裁决（CHALLENGE/REBUTTAL/SUPPLEMENT/MERGE/ACCEPT/REJECT/FINISH）
     c. 如需补证：Reviewer 补充证据
     d. 如 FINISH：退出循环
  5. ReportWriterAgent 生成标准化报告
  6. 返回 ReviewResult

辩论退出条件：
  - Lead Controller 发出 FINISH 指令
  - 达到 max_rounds 上限
  - consensus_score >= 0.8
```

---

## 11. EvidenceStore 数据中枢

```
文件：src/flows/evidence_store.py（v2 新增）

定位：所有角色的数据共享中心，贯穿整个审查流程

存储内容：
  - findings[]          : 所有 Reviewer 产出的缺陷
  - challenges[]        : Critic 的质疑记录
  - decisions[]         : Lead Controller 的裁决记录
  - policy_references[] : company_policy_reviewer 命中的公司规范
  - debate_rounds[]     : Debate 模式的多轮记录

核心方法：
  add_finding(finding)                       : 添加缺陷（自动去重）
  add_challenge(challenge)                   : 添加质疑记录
  add_decision(decision)                     : 添加裁决记录
  add_policy_reference(finding_id, policy)   : 添加政策引用
  add_debate_round(round_data)               : 添加辩论轮次
  get_findings_by_severity(level)            : 按严重级别查询
  merge_findings(target_id, source_id)       : 合并两个 findings
  remove_finding(finding_id)                 : 移除 finding
  to_dict()                                  : 序列化为字典
  save(path)                                 : 持久化到 JSON 文件
  load(path)                                 : 从 JSON 文件加载

持久化路径：output/tasks/{task_id}/evidence_store.json
```

**学习要点**：EvidenceStore 是整个 v2 架构的数据中枢，所有角色通过它共享数据，避免了角色间直接传递数据的耦合。持久化到磁盘后，Judge 可以直接读取，也方便事后复盘。

---

## 12. RAG 知识检索层 (src/rag)

> v2.4 起采用 **向量 + BM25 双路召回 + RRF 融合排序**

### 12.1 模块总览

| 文件 | 类 | 职责 |
|------|-----|------|
| `chunker.py` | `MarkdownChunker` | Markdown 语义切片（按标题/段落） |
| `vector_store.py` | `VectorStore` | pgvector 向量存储与余弦相似度检索 |
| `bm25_retriever.py` | `BM25Retriever` | BM25 关键词检索（内存倒排索引） |
| `retriever.py` | `RAGRetriever` | 双路召回编排 + RRF 融合排序 |

### 12.2 文档切片 (chunker.py)

```
功能：将企业编码规范文档切分为语义片段

切片策略：
  - 按标题层级切分（# ## ### 作为分界）
  - 大段落按段落边界二次切分，带重叠窗口
  - 保留元数据（source_file, section_title, chunk_index）

输出：Chunk 对象列表
```

### 12.3 向量存储 (vector_store.py)

```
功能：基于 pgvector 的向量存储与检索

核心方法：
  add_async(chunk, vector)           : 单条插入
  add_batch_async(chunks, vectors)   : 批量插入
  search_async(query_vec, top_k)     : 余弦相似度 Top-K
  get_all_chunks_async()             : 加载全量 chunk（供 BM25 构建索引）
  clear_async()                      : 清空所有向量

持久化：rag_vectors 表，IVFFlat 索引加速
```

### 12.4 BM25 关键词检索 (bm25_retriever.py)

> v2.4 新增，纯 Python 实现，无外部依赖

```
功能：内存倒排索引 + BM25 评分检索

BM25 参数：k1=1.5, b=0.75
分词策略：中文按单字，英文按空格/标点，过滤 <2 字符 token
IDF 预计算：build_index() 时一次性算完

核心方法：
  build_index(chunks)    : 从 Chunk 列表构建索引
  search(query, top_k)   : BM25 评分检索

典型用法：
  bm25 = BM25Retriever()
  bm25.build_index(chunks)       # 从 pgvector 加载或直接传入
  results = bm25.search("SQL injection", top_k=5)
  # -> [(Chunk, bm25_score), ...]
```

### 12.5 双路召回 + RRF 融合 (retriever.py)

```
                    Query
                      │
          ┌───────────┴───────────┐
          v                       v
  ┌───────────────┐     ┌─────────────────┐
  │ Vector Search │     │ BM25 Keyword    │
  │ (pgvector)    │     │ (in-memory)     │
  │ cosine_sim    │     │ BM25 scoring    │
  │ semantic      │     │ keyword match   │
  └───────┬───────┘     └────────┬────────┘
          │                      │
          └──────────┬───────────┘
                     v
          ┌──────────────────────┐
          │  RRF Fusion (k=60)   │
          │  score = sum(1/(k+r))│
          │  vec weight: 1.0     │
          │  bm25 weight: 0.8    │
          └──────────┬───────────┘
                     v
               Top-K Results
```

**RRF 公式：** `RRF_score(d) = sum( w_i / (k + rank_i(d)) )`
- k=60（标准常数，来自原始 RRF 论文）
- 默认权重：向量 1.0，BM25 0.8（略微偏向语义）
- 去重：以 chunk text 为唯一键，同一 chunk 在多路结果中合并得分

**降级策略：**
- 两路都可用 -> `hybrid`（RRF 融合）
- 向量不可用 -> `bm25-only`（纯关键词兜底）
- BM25 不可用 -> `vector-only`（纯语义）

---

## 13. 报告层 (src/report)

### 13.1 缺陷数据结构 (findings.py)

```
类：FindingsCollection

功能：管理缺陷列表的结构化数据

方法：
  from_review_findings(findings_list) : 从 ReviewResult 转换
  add(finding)                        : 添加缺陷
  to_markdown()                       : 输出 Markdown 格式
  to_dict()                           : 序列化为字典
  filter_by_severity(level)           : 按严重级别过滤
```

### 13.2 报告渲染器 (report_renderer.py)

```
类：ReportRenderer（v1 兼容，v2 离线降级用）

功能：将 FindingsCollection 渲染为 Markdown 报告

模板结构：
  1. 报告标题和元数据
  2. 摘要统计（各严重级别数量）
  3. 缺陷详情列表（按严重程度排序）
  4. 修复建议汇总

注：v2 在线模式下由 ReportWriterAgent 替代
```

---

## 14. 评审打分层 (src/judge)

### 14.1 JudgeRunner (judge_runner.py)

```
类：JudgeRunner

功能：调用 Judge Agent 对报告进行六维评分

流程：
  1. 准备 judge_input（报告内容 + findings 摘要）
  2. 调用 Judge Agent
  3. 解析 JSON 评分结果
  4. 保存 judge.json + judge.md

评分维度：
  - critical_risk_coverage : 关键风险覆盖
  - evidence_quality       : 证据质量
  - risk_accuracy          : 风险准确度
  - noise_control          : 噪声控制
  - actionability          : 可操作性
  - report_clarity         : 报告清晰度

降级处理：
  模型不可用时返回默认评分（60 分）+ offline 标记
```

---

## 15. 任务调度层 (src/scheduler)

```
类：WebTaskManager

功能：管理审查任务的生命周期

任务状态机：
  PENDING → RUNNING → COMPLETED / FAILED

核心方法：
  create_task(base, target, ...) : 创建任务
  get_task(task_id)              : 获取任务信息
  list_tasks()                   : 列出所有任务
  update_status(task_id, status) : 更新状态
  get_result(task_id)            : 获取审查结果

并发控制：
  - asyncio.Semaphore 限制最大并行任务数（默认 3）
  - 异步队列执行审查流程
```

---

## 16. Web 服务层 (src/web + src/web_app.py)

### 16.1 FastAPI 应用 (web_app.py)

```
功能：创建 FastAPI 应用实例，注册路由和中间件

中间件：
  - CORS（允许跨域）
  - 静态文件挂载（/static → frontend/）

启动：uvicorn src.web_app:app --reload
```

### 16.2 API 路由 (web/routes.py)

```
POST /api/review        : 提交审查请求
GET  /api/tasks         : 列出所有任务
GET  /api/tasks/{id}    : 获取任务详情
GET  /api/tasks/{id}/report  : 获取审查报告
GET  /api/tasks/{id}/judge   : 获取评分结果
GET  /api/tasks/{id}/transcript : 获取日志转录
GET  /api/health        : 健康检查
```

---

## 17. 前端界面 (frontend)

```
技术：原生 HTML/CSS/JS（SPA，无构建工具）

主要页面：
  - 首页：提交 PR 审查请求
  - 任务列表：查看所有审查任务
  - 任务详情：查看审查报告、评分、日志
  - 评分可视化：Chart.js 六维雷达图

交互方式：
  - fetch API 调用后端接口
  - 轮询任务状态直到完成
```

---

## 18. 入口文件

### 18.1 CLI 入口 (src/main.py)

```
功能：命令行提交审查

用法：
  python -m src.main --base main --target feature-branch

流程：
  1. 解析命令行参数
  2. 加载配置
  3. 创建 AgentFactory
  4. 执行审查流程
  5. 输出报告和评分
```

### 18.2 Web 入口 (src/web_app.py)

```
功能：启动 FastAPI Web 服务

用法：
  uvicorn src.web_app:app --host 0.0.0.0 --port 8000
```

---

## 19. 数据流转全景

### 19.1 Council 模式数据流

```
用户提交 PR
    │
    ├── TaskManager.create_task()
    │
    ├── AgentFactory.create_all()
    │   ├── create_reviewers()                 → Reviewer x5
    │   ├── create_company_policy_reviewer()   → company_policy_reviewer
    │   ├── create_critic()                    → Critic
    │   ├── create_lead_controller()           → Lead Controller
    │   ├── create_report_writer()             → ReportWriterAgent
    │   └── create_judge()                     → Judge
    │
    ├── GitOps.get_diff()
    │
    ├── CouncilFlow.execute()
    │   ├── [Step 1] Reviewer x5 并行扫描
    │   │   └── 每个 Reviewer → JSON findings[]
    │   │
    │   ├── [Step 2] company_policy_reviewer 独立审查
    │   │   └── risk_scan + retrieve_company_policy → findings[] + policy_references
    │   │
    │   ├── [Step 3] 所有 findings 写入 EvidenceStore
    │   │
    │   ├── [Step 4] 程序化合并（_programmatic_merge）去重
    │   │
    │   ├── [Step 5] Lead Controller 一次性裁决
    │   │   └── ACCEPT / REJECT / DOWNGRADE
    │   │
    │   └── [Step 6] ReportWriterAgent 生成报告
    │
    ├── EvidenceStore.save()  → evidence_store.json
    │
    ├── JudgeRunner.run()
    │   └── 六维评分 → JudgeResult
    │
    └── 更新 TaskInfo 状态为 COMPLETED
```

### 19.2 Debate 模式数据流

```
用户提交 PR
    │
    ├── [同 Council Step 1-4]
    │
    ├── DebateFlow.execute()
    │   ├── Reviewer x5 + company_policy_reviewer 并行扫描
    │   ├── EvidenceStore 收集所有 findings
    │   ├── 程序化合并去重
    │   │
    │   ├── [辩论循环] 最多 max_rounds 轮
    │   │   │
    │   │   ├── Critic 质疑 → CHALLENGE / DOWNGRADE / MERGE / REJECT
    │   │   │
    │   │   ├── Lead Controller 裁决
    │   │   │   ├── CHALLENGE  → 要求 Reviewer 补证
    │   │   │   ├── REBUTTAL   → 要求 Reviewer 反驳
    │   │   │   ├── SUPPLEMENT → 补充查看文件
    │   │   │   ├── MERGE      → 合并 findings
    │   │   │   ├── ACCEPT     → 接受 finding
    │   │   │   ├── REJECT     → 拒绝 finding
    │   │   │   └── FINISH     → 结束辩论
    │   │   │
    │   │   └── EvidenceStore 记录每轮结果
    │   │
    │   └── ReportWriterAgent 生成报告
    │
    ├── EvidenceStore.save()  → evidence_store.json
    │
    ├── JudgeRunner.run()
    │   └── 六维评分 → JudgeResult
    │
    └── 更新 TaskInfo 状态为 COMPLETED
```

---

## 20. 演示仓库 (demo)

demo/payment_repo/ 包含故意埋入缺陷的支付业务代码，用于快速演示：

### config.py 缺陷：
- 硬编码数据库密码 DB_PASSWORD = "admin123"
- SSL 验证禁用 VERIFY_SSL = False

### payment.py 缺陷：
- 硬编码 API 密钥和 Secret Token
- SQL 注入（字符串拼接查询）
- eval() 危险调用
- 无幂等性检查（重复支付风险）
- 裸 except 异常捕获
- 退款无金额校验
- 调试 print 语句
- Webhook 签名验证被禁用
- 银行卡号明文存储

### test_payment.py 缺陷：
- 测试无断言（永远通过）
- 测试覆盖率极低

---

## 21. 测试策略 (tests)

### 21.1 测试覆盖范围

| 测试文件 | 覆盖模块 | 测试重点 |
|---------|---------|---------|
| test_config.py | config_loader | 配置加载、环境变量替换、离线检测 |
| test_logger.py | logger | 日志级别、JSONL 转录、文件输出 |
| test_git_ops.py | git_ops | diff 获取、文件内容、异常处理 |
| test_core_utils.py | file_utils, serializer | 路径验证、JSON 序列化/反序列化 |
| test_mimo_wrapper.py | mimo_wrapper | 模型创建、JSON 提取、离线降级 |
| test_embedding.py | embedding | 向量生成、余弦相似度、离线降级 |
| test_agents.py | agent_factory, reviewer, company_policy | 智能体创建、角色配置、向后兼容 |
| test_tools.py | read_file, search_code | 文件读取、代码搜索、权限控制 |
| test_flows.py | simple_flow, base_flow | 规则检测、性能、多文件处理 |
| test_council_v2.py | council_flow | 程序化合并、JSON 解析、去重 |
| test_debate_v2.py | debate_flow | 辩论动作路由、共识判断、轮次记录 |
| test_evidence_store.py | evidence_store | CRUD、去重、持久化、政策引用 |
| test_lead_controller.py | lead_controller | 输出解析、Council/Debate 动作验证 |
| test_report_writer.py | report_writer | Agent 创建、fallback 渲染、政策引用 |
| test_rag.py | chunker, vector_store, retriever | 切片、向量检索、降级处理 |
| test_report.py | findings, report_renderer | 缺陷管理、报告渲染 |
| test_judge.py | judge_runner | 评分解析、离线降级 |
| test_task_manager.py | task_manager | 任务 CRUD、状态机、并发控制 |
| test_web_api.py | web routes | 全部 API 端点集成测试 |

### 21.2 测试运行

```bash
# 运行全部测试
python -m pytest tests/ -v

# 运行 v2 相关测试
python -m pytest tests/test_agents.py tests/test_council_v2.py tests/test_debate_v2.py tests/test_evidence_store.py tests/test_lead_controller.py tests/test_report_writer.py -v
```

### 21.3 测试设计要点

- 使用 tmp_path fixture 隔离文件系统操作
- 使用 monkeypatch 模拟环境变量
- 异步测试使用 @pytest.mark.asyncio
- Web API 测试使用 FastAPI TestClient
- 性能测试验证 100 行 diff < 10 秒
- v2 测试验证 144/144 通过

---

## 22. 关键设计思想总结

### 22.1 架构层面

- **分层解耦**：五层单向依赖，无循环耦合，每层可独立测试和替换
- **流程引擎模式**：不同审查模式封装为独立 Flow 类，通过工厂创建
- **策略模式**：SimpleFlow/CouncilFlow/DebateFlow 实现同一接口，运行时切换
- **模板方法模式**：BaseFlow.execute() 提供统一框架，子类实现 run()
- **数据中枢模式**：EvidenceStore 作为所有角色的数据共享中心，避免角色间直接耦合
- **三层模型模式**：AgentFactory 按角色复杂度分配不同级别模型，成本与能力平衡
- **数据库一体化**：PostgreSQL + pgvector 同时承载结构化数据和向量检索，减少中间件依赖

### 22.2 安全层面

- **最小权限**：工具默认只读，写操作需显式启用
- **路径白名单**：文件访问限制在允许的目录内
- **密钥隔离**：API 密钥仅存 .env，不进前端、不打日志
- **命令白名单**：测试执行工具限制可执行的命令

### 22.3 可靠性层面

- **优雅降级**：模型不可用时切换到离线模式（SimpleFlow 规则扫描）
- **RAG 降级**：知识库不可用时返回空，不影响审查流程
- **报告降级**：ReportWriterAgent 不可用时使用 fallback_render()
- **超时重试**：模型调用支持配置化的重试机制
- **并发控制**：信号量限制最大并行任务数

### 22.4 可维护性层面

- **配置外部化**：Prompt 模板、模型参数、流程配置全部外部文件管理
- **结构化日志**：JSONL 格式便于检索和分析
- **标准化输出**：所有缺陷统一 JSON Schema
- **单例配置**：ConfigLoader 全局唯一，避免配置不一致
- **向后兼容**：SCANNER_ROLES / create_scanner_agent / create_scanners 作为别名保留

### 22.5 值得深入学习的技术点

1. **AgentScope 框架**：如何用 Agent/Toolkit/Msg 构建多智能体系统
2. **异步编程**：asyncio.gather 并发、信号量控制、异步 HTTP 调用
3. **RAG 实现**：切片 → pgvector 向量化 → 余弦相似度检索的完整链路
4. **EvidenceStore 设计**：数据中枢模式，PostgreSQL 实时持久化 + 跨任务查询
5. **Lead Controller 调度**：Council 一次性裁决 vs Debate 多轮动态调度
6. **三层模型架构**：按角色复杂度分配模型，不同厂商保证辩论多样性
7. **pgvector 一体化**：结构化数据 + 向量检索共用 PostgreSQL，减少中间件
8. **降级策略**：系统在部分组件不可用时仍能正常工作
9. **Docker 部署**：docker-compose 一键部署 PostgreSQL + pgvector
10. **前端 SPA**：原生 JS 实现的无框架单页应用
