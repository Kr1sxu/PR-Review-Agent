# PR-Review Agent 项目实施计划

> 本文档为 PR-Review Agent 从 0 到 1 的完整构建路线图。
> 基于 AgentScope 多智能体框架 + MiMo 大模型，采用分层递进式开发。
> 每个阶段完成后可独立验证，确保阶段性成果可用。
> 编写的代码必要部分需要加上中文注释
> 每完成一项开发，在此文件上该项的checklist上打勾。
> 除了项目整体的README技术文档外，大的模块功能构建后也要在对应文件夹下留下该模块的README文档
> 每完成一个阶段后停下来，报告给用户，等待用户命令继续构建项目

---

## 整体目录结构规划

`
PR-Review-Agent/
├── .env                          # 环境变量（MiMo/向量密钥，不提交Git）
├── .env.example                  # 环境变量模板
├── requirements.txt              # Python 依赖清单
├── README.md                     # 项目说明文档
├── config/
│   ├── settings.yaml             # 全局配置（模型地址、路径、参数）
│   └── prompts/                  # 所有 Prompt 模板（yaml/txt）
│       ├── scanner.txt
│       ├── debater.txt
│       ├── merger.txt
│       ├── judge.txt
│       └── ...
├── knowledge_base/               # 企业规范知识库（Markdown）
│   ├── security.md
│   ├── payment.md
│   ├── testing.md
│   └── ...
├── demo/                         # 内置 payment 风险 demo
│   └── payment_repo/
├── frontend/                     # Web 前端（原生 HTML/CSS/JS）
│   ├── index.html
│   ├── css/
│   ├── js/
│   └── assets/
├── src/
│   ├── __init__.py
│   ├── main.py                   # CLI 入口
│   ├── web_app.py                # FastAPI Web 入口
│   ├── core/                     # 底层支撑层
│   │   ├── __init__.py
│   │   ├── git_ops.py            # Git 操作封装
│   │   ├── file_utils.py         # 文件读写工具
│   │   ├── serializer.py         # JSON 序列化工具
│   │   ├── logger.py             # 日志管理
│   │   └── config_loader.py      # .env / yaml 配置加载
│   ├── models/                   # 模型封装层
│   │   ├── __init__.py
│   │   ├── mimo_wrapper.py       # MiMo ModelWrapper（继承 AgentScope ModelBase）
│   │   └── embedding.py          # text-embedding-v4 向量客户端
│   ├── agents/                   # 智能体定义
│   │   ├── __init__.py
│   │   ├── scanner_agent.py      # Scanner 扫描智能体
│   │   ├── debater_agent.py      # Debater 辩论智能体
│   │   ├── merger_agent.py       # Merger 合并智能体
│   │   ├── judger_agent.py       # Judge 评估智能体
│   │   └── agent_factory.py      # 智能体工厂（统一创建/注册）
│   ├── tools/                    # AgentScope 工具注册
│   │   ├── __init__.py
│   │   ├── read_file.py          # 文件读取工具
│   │   ├── search_code.py        # 代码搜索工具
│   │   ├── run_tests.py          # 测试执行工具（默认禁用）
│   │   └── tool_registry.py      # 工具统一注册
│   ├── flows/                    # 审查流程编排
│   │   ├── __init__.py
│   │   ├── base_flow.py          # 流程基类
│   │   ├── debate_flow.py        # Debate 辩论流程
│   │   ├── council_flow.py       # Council 基线流程
│   │   ├── simple_flow.py        # Simple 离线降级流程
│   │   └── agentic_flow.py       # Agentic 自主流程
│   ├── rag/                      # RAG 检索模块
│   │   ├── __init__.py
│   │   ├── chunker.py            # Markdown 文本切片
│   │   ├── vector_store.py       # 向量缓存与检索
│   │   └── retriever.py          # RAG 检索入口
│   ├── report/                   # 报告生成
│   │   ├── __init__.py
│   │   ├── findings.py           # 结构化缺陷数据管理
│   │   └── report_renderer.py    # Markdown 报告渲染
│   ├── judge/                    # AI Judge 评估
│   │   ├── __init__.py
│   │   └── judge_runner.py       # Judge 打分执行
│   ├── scheduler/                # 任务调度层
│   │   ├── __init__.py
│   │   └── task_manager.py       # WebTaskManager 异步任务队列
│   └── web/                      # Web API 路由
│       ├── __init__.py
│       ├── routes_task.py        # 任务 CRUD 接口
│       ├── routes_report.py      # 报告/文件读取接口
│       ├── routes_config.py      # 配置接口
│       └── routes_score.py       # 打分接口
├── tests/                        # 单元测试
│   ├── test_git_ops.py
│   ├── test_mimo_wrapper.py
│   ├── test_embedding.py
│   ├── test_agents.py
│   ├── test_flows.py
│   ├── test_rag.py
│   ├── test_report.py
│   ├── test_web_api.py
│   └── test_task_manager.py
├── outputs/                      # 运行输出目录（Git忽略）
│   └── {task_id}/
│       ├── report.md
│       ├── findings.json
│       ├── judge.json
│       ├── judge.md
│       └── transcript.jsonl
└── task_store.json               # Web 任务状态持久化
`

---

## 阶段一：项目脚手架与环境配置

**目标**：搭建项目骨架，配置开发环境，确保依赖可安装、项目可运行。

### 1.1 初始化项目结构
- [√] 创建上图完整目录结构（空 __init__.py、空目录）
- [√] 初始化 Git 仓库，配置 .gitignore（忽略 .env、outputs/、__pycache__、	ask_store.json）

### 1.2 依赖管理
- [√] 编写 
equirements.txt，核心依赖：
  - gentscope — 多智能体框架
  - astapi + uvicorn — Web 服务
  - httpx / iohttp — 异步 HTTP 客户端（MiMo/向量接口调用）
  - pydantic — 数据校验
  - python-dotenv — .env 加载
  - pyyaml — YAML 配置读取
  - pytest + pytest-asyncio — 测试框架
- [√] 创建虚拟环境并验证 pip install -r requirements.txt 可正常安装

### 1.3 配置体系
- [√] 编写 .env.example 模板：
  `
  MIMO_API_URL=https://xxx
  MIMO_API_KEY=sk-xxx
  MIMO_MODEL_NAME=mimo-xxx
  EMBEDDING_API_URL=https://xxx
  EMBEDDING_API_KEY=sk-xxx
  `
- [√] 编写 config/settings.yaml 全局配置（模型参数、路径、并发数、辩论轮次等）
- [√] 实现 src/core/config_loader.py — 统一加载 .env + settings.yaml

---

## 阶段二：底层支撑层（core 模块）

**目标**：实现所有底层工具模块，为上层业务提供基础设施。

### 2.1 Git 操作封装
- [√] 实现 src/core/git_ops.py：
  - get_diff(base_commit, target_commit, repo_path) — 获取两个 commit 之间的 diff
  - get_file_content(commit, filepath, repo_path) — 获取指定 commit 的文件内容
  - list_changed_files(base_commit, target_commit, repo_path) — 变更文件列表
  - 支持标准 commit hash、分支名、HEAD~N 相对引用
  - 统一异常处理（仓库不存在、commit 无效等）

### 2.2 文件与序列化工具
- [√] 实现 src/core/file_utils.py — 安全文件读写、路径校验（只读约束）
- [√] 实现 src/core/serializer.py — JSON 序列化/反序列化（处理 datetime、自定义对象）

### 2.3 日志系统
- [√] 实现 src/core/logger.py：
  - 接入 AgentScope 日志回调
  - 每个任务独立 	ranscript.jsonl 文件
  - 支持 INFO / WARNING / ERROR / AGENT_ACTION 等级别
  - 日志格式：{timestamp, task_id, level, source, message, metadata}

### 2.4 单元测试
- [√] 	ests/test_git_ops.py — 测试 diff 获取、文件内容读取、异常处理
- [√] 	ests/test_logger.py — 测试日志写入、任务隔离

---

## 阶段三：模型封装层

**目标**：完成 MiMo 和 text-embedding-v4 的接口封装，实现离线降级。

### 3.1 MiMo ModelWrapper
- [√] 实现 src/models/mimo_wrapper.py：
  - 继承 AgentScope ModelBase，实现 __call__ 方法
  - HTTP 请求封装（支持配置 base_url、api_key、model_name）
  - 超时重试机制（可配置重试次数、间隔）
  - JSON 输出强制校验（正则提取 JSON，失败重试）
  - 注册至 AgentScope 全局模型池
  - **离线降级**：密钥缺失或连接失败时返回模拟响应，标记 offline=True

### 3.2 Embedding 客户端
- [√] 实现 src/models/embedding.py：
  - 封装 text-embedding-v4 HTTP 调用
  - 单条/批量 embedding 接口
  - 超时与异常处理，失败时返回空向量并标记降级
  - **独立模块**，不接入 AgentScope 模型池

### 3.3 单元测试
- [√] 	ests/test_mimo_wrapper.py — 测试正常调用、JSON 校验、离线降级
- [√] 	ests/test_embedding.py — 测试正常调用、批量处理、降级行为

---

## 阶段四：智能体与工具层（agents + tools）

**目标**：基于 AgentScope 创建多角色智能体，注册只读工具集。

### 4.1 工具注册
- [√] 实现 src/tools/read_file.py — 只读读取仓库文件内容
- [√] 实现 src/tools/search_code.py — 代码关键词/正则搜索
- [√] 实现 src/tools/run_tests.py — 测试执行（**默认禁用**，仅用户显式传入命令时启用）
- [√] 实现 src/tools/tool_registry.py — 统一注册所有工具至 AgentScope，**强制只读约束**

### 4.2 智能体定义
- [√] 实现 src/agents/scanner_agent.py — Scanner 扫描智能体
  - 角色：安全专家 / 逻辑审查员 / 测试工程师 / 可维护性审查员 / 规范检查员
  - 输入：代码 diff + PR 描述
  - 输出：结构化缺陷列表（JSON Schema）

- [√] 实现 src/agents/debater_agent.py — Debater 辩论智能体
  - 角色：辩论者 + 仲裁者
  - 功能：多轮辩论、合并重复缺陷、补充证据、校准风险等级
  - 辩论终止条件：共识达成 或 达到最大轮次

- [√] 实现 src/agents/merger_agent.py — Merger 合并智能体
  - 功能：合并多角色 Scanner 输出，去除重复，统一格式

- [√] 实现 src/agents/judger_agent.py — Judge 评估智能体
  - 六维评分：关键风险覆盖、证据质量、风险准确度、重复噪音控制、修复可执行度、报告清晰度
  - 输出：结构化分数 + 文字评价

- [√] 实现 src/agents/agent_factory.py — 智能体工厂
  - 统一创建、配置、注册所有智能体
  - 根据模式（online/offline）选择真实模型或离线模拟

### 4.3 单元测试
- [√] 	ests/test_agents.py — 测试智能体创建、离线模式响应
- [√] 	ests/test_tools.py — 测试工具只读约束、参数校验

---

## 阶段五：RAG 知识库检索模块

**目标**：实现本地 Markdown 知识库的切片、向量化、检索能力。

### 5.1 文本切片
- [√] 实现 src/rag/chunker.py：
  - 按 Markdown 标题/段落语义切片
  - 可配置 chunk_size 与 overlap
  - 保留元数据（来源文件、章节标题）

### 5.2 向量存储与检索
- [√] 实现 src/rag/vector_store.py：
  - 内存级向量缓存（启动时计算，运行期间复用）
  - 余弦相似度检索 Top-K
  - 向量缓存持久化（可选，避免重复计算）

- [√] 实现 src/rag/retriever.py：
  - 统一检索入口：query → 切片向量 → Top-K 结果
  - 每条缺陷自动绑定匹配的规范索引
  - RAG 失败时优雅降级（返回空结果，不阻塞流程）

### 5.3 知识库内容
- [√] 编写 knowledge_base/security.md — 安全编码规范
- [√] 编写 knowledge_base/payment.md — 支付业务规范
- [√] 编写 knowledge_base/testing.md — 测试规范

### 5.4 单元测试
- [√] 	ests/test_rag.py — 测试切片、检索、降级行为

---

## 阶段六：审查流程编排（flows）

**目标**：实现四种审查流程，统一由流程基类派生。

### 6.1 流程基类
- [√] 实现 src/flows/base_flow.py：
  - 定义统一接口：
un(diff, pr_desc, config) → findings
  - 统一错误处理与日志记录
  - 统一输出格式（indings.json Schema）

### 6.2 Simple 离线流程（优先实现，用于验证基础链路）
- [√] 实现 src/flows/simple_flow.py：
  - 无模型调用，基于规则/正则的静态分析
  - 输出基础缺陷列表（用于离线降级演示）
  - **性能要求**：100 行变更 ≤ 10 秒

### 6.3 Council 基线流程
- [√] 实现 src/flows/council_flow.py：
  - 固定流水线：Scanner 并行扫描 → Merger 合并 → 报告生成
  - 无辩论环节，作为基准对照

### 6.4 Debate 辩论流程（核心）
- [√] 实现 src/flows/debate_flow.py：
  - Scanner 并行扫描 → Merger 合并 → Debater 多轮辩论 → 报告生成
  - 辩论循环：自动合并重复、补充证据、校准风险
  - 可配置最大辩论轮次（默认 3 轮）
  - **性能要求**：常规变更 ≤ 5 分钟

### 6.5 Agentic 自主流程
- [√] 实现 src/flows/agentic_flow.py：
  - 更高级的自主决策流程（可参考二期拓展）

### 6.6 单元测试
- [√] 	ests/test_flows.py — 测试四种流程的输入输出、异常处理、离线降级

---

## 阶段七：报告生成与 AI Judge

**目标**：生成结构化审查报告和 AI 打分。

### 7.1 缺陷数据管理
- [√] 实现 src/report/findings.py：
  - 定义缺陷数据结构（severity、category、file、line、description、evidence、spec_reference）
  - indings.json 的读写与校验

### 7.2 报告渲染
- [√] 实现 src/report/report_renderer.py：
  - 将 indings.json 渲染为 
eport.md
  - 按风险等级分组展示（Critical / High / Medium / Low）
  - 每条缺陷附带：代码证据、修复建议、规范引用

### 7.3 AI Judge 评估
- [√] 实现 src/judge/judge_runner.py：
  - 读取 judge_input.json（报告摘要 + 结构化数据）
  - 独立 Judge 会话，不受报告文笔影响
  - 输出 judge.json + judge.md
  - 六维评分可视化数据格式

### 7.4 单元测试
- [√] 	ests/test_report.py — 测试报告渲染、JSON Schema 校验
- [√] 	ests/test_judge.py — 测试打分输出、异常处理

---

## 阶段八：任务调度层

**目标**：实现异步任务管理，连接 Web/CLI 入口与流程执行。

### 8.1 WebTaskManager
- [√] 实现 src/scheduler/task_manager.py：
  - 异步任务队列（asyncio）
  - 最大并发 3 个任务，超出排队等待
  - 任务生命周期管理：pending → running → completed / failed
  - 任务状态持久化至 	ask_store.json
  - 统一初始化 AgentScope 环境、模型池、工具注册、知识库
  - 根据 mode 参数分发至对应流程

### 8.2 单元测试
- [√] 	ests/test_task_manager.py — 测试任务创建、状态流转、并发限制

---

## 阶段九：Web API 与前端

**目标**：完成 FastAPI 后端接口和轻量前端页面。

### 9.1 FastAPI 后端
- [√] 实现 src/web_app.py — FastAPI 应用入口，挂载路由、静态文件、CORS
- [√] 实现 src/web/routes_task.py：
  - POST /api/tasks — 创建审查任务
  - GET /api/tasks — 任务列表
  - GET /api/tasks/{id} — 任务详情 + 实时进度
  - DELETE /api/tasks/{id} — 删除任务
  - POST /api/tasks/{id}/restart — 重启任务
- [√] 实现 src/web/routes_report.py：
  - GET /api/tasks/{id}/report — 读取报告文件
  - GET /api/tasks/{id}/findings — 读取缺陷 JSON
  - GET /api/tasks/{id}/transcript — 读取日志（支持关键词搜索）
- [√] 实现 src/web/routes_score.py：
  - POST /api/tasks/{id}/judge — 触发 AI 打分
  - GET /api/tasks/{id}/judge — 获取打分结果
- [√] 实现 src/web/routes_config.py：
  - GET /api/config — 读取当前配置（密钥脱敏）
  - PUT /api/config — 更新配置

### 9.2 Web 前端页面
- [√] rontend/index.html — SPA 主页面框架
- [ ] **任务总览页** — 历史任务列表，展示模式、总分、状态，支持重启/删除
- [ ] **新建任务页** — 表单：仓库路径、commit 范围、PR 文档、模式选择、RAG 开关、辩论轮次
- [√] **实时进度页** — 长轮询刷新：执行阶段、辩论轮次、缺陷数量、异常提示
- [ ] **审查结果页** — 风险分级卡片、Markdown 报告预览、单条缺陷证据链、日志检索
- [ ] **AI 打分面板** — 六维柱状图（Chart.js / ECharts），支持 council vs debate 对比
- [√] **系统配置页** — MiMo/向量接口配置，密钥仅 .env 存储，页面不展示明文

### 9.3 CLI 入口
- [√] 实现 src/main.py — 命令行参数解析，转发至 TaskManager
  - 参数：--repo, --base, --target, --pr, --mode, --rag, --max-rounds

### 9.4 集成测试
- [√] 	ests/test_web_api.py — 测试所有 API 端点

---

## 阶段十：Demo 与文档

**目标**：内置演示用例，完善项目文档。

### 10.1 内置 Demo
- [√] 创建 demo/payment_repo/ — 模拟支付业务 Git 仓库
  - 包含典型安全/逻辑/测试缺陷的代码变更
  - 提供 base commit 和 target commit
  - 一键加载 demo 参数至 Web 表单

### 10.2 知识库规范文档
- [√] 完善 knowledge_base/ 内容，覆盖安全、支付、测试三类规范

### 10.3 项目文档
- [√] 编写 README.md：
  - 项目简介与架构图
  - 环境部署步骤（Python 版本、虚拟环境、依赖安装）
  - .env 配置说明
  - Web 启动方式（uvicorn src.web_app:app --host 127.0.0.1 --port 8000）
  - CLI 使用方式
  - 页面功能截图说明
  - 输出文件说明
  - 常见问题排查

---

## 阶段十一：安全加固与非功能需求落地

**目标**：满足安全、性能、兼容性等非功能性需求。

### 11.1 安全加固
- [√] 确认所有 AgentScope 工具仅只读
- [ ] 
un_tests 默认禁用，仅用户显式配置时启用
- [√] 密钥仅 .env 存储，日志/前端/响应中不泄露
- [√] 敏感扫描结果页面脱敏处理
- [√] Web 服务绑定 127.0.0.1，禁止  .0.0.0

### 11.2 性能验证
- [√] Simple 模式：100 行变更 ≤ 10 秒
- [√] Debate 模式：常规变更 ≤ 5 分钟
- [√] 向量检索 ≤ 2 秒
- [√] 长轮询刷新延迟 ≤ 1 秒
- [√] 最大并发 3 个任务验证

### 11.3 兼容性
- [√] Windows / macOS / Linux 启动验证
- [√] Python 3.9+ 兼容性验证
- [√] Git commit / 分支 / HEAD~N 引用测试
- [√] 密钥缺失自动降级 + 页面提示

### 11.4 可维护性检查
- [√] 代码分层解耦验证（Web → Scheduler → Flow → Agent → Tools）
- [√] Prompt / 规范 / 参数全部外部配置化，无硬编码
- [√] 单元测试覆盖率检查

---

## 实施建议

| 优先级 | 说明 |
|--------|------|
| **P0** | 阶段一～三（脚手架 → core → 模型封装），约 2-3 天 |
| **P0** | 阶段四（智能体 + 工具），约 2 天 |
| **P0** | 阶段五（RAG）+ 阶段六（流程编排），约 3 天 |
| **P1** | 阶段七（报告 + Judge）+ 阶段八（调度层），约 2 天 |
| **P1** | 阶段九（Web + 前端），约 3-4 天 |
| **P2** | 阶段十（Demo + 文档）+ 阶段十一（加固），约 2 天 |

**总预估工时**：14-18 个工作日（单人全栈开发）

### 开发节奏建议
1. **先跑通 Simple 离线模式**：阶段一～三完成后立即验证基础链路（diff → 规则扫描 → 报告）
2. **再接入真实模型**：阶段四完成后用 MiMo 在线模式跑通 Council 流程
3. **核心亮点最后打磨**：Debate 辩论流程是项目核心差异化，建议在基础链路稳定后再开发
4. **前端可并行**：在后端 API Schema 确定后，前端可独立并行开发

---

## 关键技术决策记录

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 智能体框架 | AgentScope | 需求文档指定，原生支持多智能体协作 |
| 生成模型 | MiMo | 需求文档指定，兼容标准 HTTP 接口 |
| 向量模型 | text-embedding-v4 | 需求文档指定，独立于 AgentScope 模型池 |
| Web 框架 | FastAPI | 原生 async 支持，与 AgentScope 异步兼容 |
| 前端方案 | 原生 HTML/CSS/JS | 轻量、无构建工具依赖、快速交付 |
| 向量存储 | 内存级 + 缓存文件 | 一期轻量，二期可迁移 Chroma |
| 任务持久化 | JSON 文件 | 单机单用户场景，无需数据库 |
| 图表库 | Chart.js 或 ECharts | 六维评分可视化，轻量易集成 |
