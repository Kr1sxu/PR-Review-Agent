# PR-ReviewAgent项目需求说明书
## 文档说明
本文档用于交付研发人员从零开发，整体智能体调度基于AgentScope框架实现，前端采用Web可视化交互，生成模型统一使用MiMo，向量嵌入保留text-embedding-v4，包含项目概述、完整技术架构、功能需求、非功能需求、数据需求、约束边界、二期拓展规划。

# 一、项目整体概述
## 1.1 项目目标
开发一套基于Python、AgentScope多智能体框架、MiMo大模型的自动化PR代码审查系统，采用辩论式多智能体协作架构，解决传统固定流水线代码审查存在重复告警、证据缺失、风险等级误判、难以对齐企业规范等痛点。
系统提供Web可视化操作界面，同时保留CLI命令行备用；内置两套审查流程（动态Debate辩论流程、固定Council基线流程），配套本地企业知识库RAG检索、全链路运行日志、AI自动打分评估模块；支持无模型密钥本地离线降级演示，所有智能体通信、工具调用、多轮对话由AgentScope统一托管。

## 1.2 核心使用人群
1. 后端开发人员：通过Web页面上传仓库配置、发起代码审查，一键获取标准化风险清单，降低人工评审沟通成本；
2. 代码评审负责人：Web端可视化对比两套审查流程打分、批量查看代码风险、统一落地企业编码规范；
3. 研发效能/算法开发：学习基于AgentScope搭建多轮辩论多智能体、工具调用、本地RAG落地实践。

## 1.3 核心业务价值
1. 多角色智能体分工自动扫描安全、逻辑、测试、可维护、企业规范五类代码缺陷，替代基础人工评审；
2. 依托AgentScope实现多轮辩论循环，自动合并重复问题、补充代码证据、校准风险等级，大幅降低误报噪音；
3. 本地RAG知识库绑定企业安全、支付、测试规范，每条缺陷附带规范原文依据，避免大模型主观臆断；
4. Web可视化任务管理、报告预览、打分图表、日志检索，整套审查流程可视化、可复现；
5. 全流程操作日志持久留存，可在线复盘智能体交互过程，便于持续优化提示词与审查策略。

# 二、整体技术架构设计
## 2.1 架构分层总览（自上而下五层单向依赖，无循环耦合）
1. 交互接入层：Web前端为主、CLI命令行备用
2. 任务调度层：FastAPI异步任务管理器，对接AgentScope运行实例
3. 智能体业务层：基于AgentScope基座构建智能体、工具、辩论流程、RAG、报告、打分模块
4. 底层支撑层：Git操作、文件IO、序列化、MiMo/向量模型网络请求、日志存储
5. 环境支撑层：虚拟环境、配置读取、依赖管理、单元测试

## 2.2 分层详细说明
### 2.2.1 第一层：交互接入层（Web为主，CLI兼容备用）
#### 1）Web前端交互模块（核心入口）
1. 技术组件：FastAPI后端接口 + 原生HTML/CSS/JS轻量前端
2. 页面功能：
    - 任务总览：展示所有历史任务，包含运行模式、总分、执行状态，支持重启、删除任务；
    - 新建任务表单：填写本地仓库路径、基线commit、目标commit、PR文档，选择运行模式、开关RAG、自定义知识库、最大辩论轮次；
    - 实时进度页：长轮询刷新执行阶段、辩论轮次、已识别缺陷数量、运行异常提示；
    - 审查结果页：风险分级卡片展示、在线预览Markdown报告、查看单条缺陷完整证据链、检索执行日志；
    - AI打分面板：可视化六维评分柱状图，支持对比council/debate两套流程得分；
    - 系统配置页：配置MiMo接口地址、text-embedding-v4向量接口、本地知识库路径，密钥仅存储.env，前端不展示明文。
3. 接口能力：任务创建/状态查询/文件读取/打分触发/配置保存，异步执行避免页面阻塞。

#### 2）CLI备用交互模块
保留完整原有命令行参数，用于脚本自动化、无前端本地调试，参数最终转发至任务调度层启动AgentScope实例。

### 2.2.2 第二层：任务调度层
核心组件：WebTaskManager
1. 职责：接收Web/CLI请求，创建异步任务队列，限制最大并发任务数；
2. 统一初始化AgentScope运行环境、模型池、工具注册、知识库；
3. 隔离上层交互与底层智能体逻辑，任务状态持久化本地task_store.json；
4. 根据mode参数分发Debate/Council/Simple/Agentic四类流程实例。

### 2.2.3 第三层：智能体业务层（基于AgentScope基座开发）
整套多智能体、工具、会话、消息通信全部依托AgentScope原生能力，自研业务模块仅负责数据存储、报告渲染、RAG检索：
#### 子模块1：AgentScope基座基础封装
1. 自定义MiMo ModelWrapper：继承AgentScope ModelBase，封装MiMo HTTP请求、超时重试、JSON格式强制校验，注册至全局模型池；
2. 工具注册：将所有Git只读工具通过AgentScope register_tool注册，配置只读权限，禁止文件修改/删除；
3. 消息体系：统一使用AgentScope Msg完成智能体间质疑、辩解、指令交互；
4. 会话管理：Debate、Council两套流程对应两套AgentScope会话循环，自动记录会话日志对接系统transcript；
5. 智能体基类扩展：所有评审、Critic、Lead、Report、Judge智能体继承AgentScope AgentBase，加载Skill审查规范作为初始prompt。

#### 子模块2：受控只读工具集合（注册至AgentScope）
git_diff、changed_files、read_file_context、search_code、secret_scan、受控run_tests（仅用户传入命令才可执行），全部只读权限。

#### 子模块3：Skill规范加载模块
读取本地Markdown审查标准、风险分级、缺陷输出格式，程序加载后注入所有AgentScope智能体初始化上下文，支持文档热更新。

#### 子模块4：企业本地RAG知识库（独立于AgentScope）
1. 读取Markdown企业规范文档，自动文本切片；
2. 向量请求独立调用text-embedding-v4，不接入AgentScope模型池；
3. 混合检索：向量相似度匹配为主，无密钥自动降级关键词检索；
4. 三层检索注入：全局前置上下文、缺陷匹配规范、独立规范审查智能体主动检索；
5. Web页面可一键开关RAG用于消融对比实验。

#### 子模块5：多智能体集群（全部基于AgentScope AgentBase）
1. 专业评审智能体：安全、正确性、测试、可维护性、企业规范审查Agent；
2. 质检智能体：Critic Agent，负责反向质疑缺陷证据、重复校验；
3. 流程控制智能体：Lead Debate Controller，通过AgentScope循环下发质疑、补证、合并、驳回等动作；
4. 输出智能体：ReportWriter Agent，仅输出固定结构JSON；
5. 评估智能体：AI Judge Agent，使用MiMo完成六维标准化打分。

#### 子模块6：Debate动态辩论循环（依托AgentScope会话循环）
1. 自研业务数据组件：
    - FindingLifecycle：管理缺陷候选/质疑/接受/驳回/降级全生命周期；
    - EvidenceStore：存储缺陷绑定代码行、上下文、质疑辩解、企业规范引用完整证据链；
2. 运行逻辑：AgentScope会话循环由Lead智能体动态决策每一步操作，支持多轮迭代，区别于Council固定单轮会话。

#### 子模块7：标准化报告渲染模块
ReportWriter Agent输出固定JSON结构，本地模板引擎渲染Markdown报告，生成findings.json、judge_input.json，供Web前端解析与AI打分使用。

#### 子模块8：AI Judge评估模块
独立启动AgentScope Judge智能体，仅读取标准化judge_input.json，输出结构化打分数据，Web可视化展示分数。

### 2.2.4 第四层：底层基础支撑层
1. 模型网络层
    - MiMo：自定义AgentScope适配器，用于所有智能体对话；
    - text-embedding-v4：独立requests请求，仅RAG向量计算使用；
2. Git工具层：调用系统Git命令解析diff、commit、文件变更；
3. 文件持久化：统一管理.review-agent输出目录、知识库、配置文件读写；
4. 日志序列化：AgentScope会话日志回调写入全局transcript.jsonl，存储所有智能体动作、工具调用、模型返回；
5. 数据序列化：标准json/jsonl处理缺陷、任务、打分、日志数据。

### 2.2.5 第五层：环境支撑层
1. 多平台虚拟环境启动脚本；
2. python-dotenv读取.env存储MiMo、向量模型密钥；
3. requirements统一依赖清单，包含AgentScope、FastAPI、uvicorn等；
4. pytest单元测试：覆盖工具调用、AgentScope会话、RAG降级、JSON解析、Web接口。

## 2.3 完整业务数据流
### 数据流1：Web前端发起审查
1. 用户填写表单提交HTTP请求 → FastAPI接口参数校验；
2. WebTaskManager创建异步任务，初始化AgentScope全局环境、注册工具、加载知识库与审查规范；
3. AgentScope启动多评审智能体，调用Git工具获取代码变更；
4. RAG独立调用text-embedding-v4检索相关企业规范注入会话上下文；
5. AgentScope会话进入Debate循环：Lead动态下发动作，Critic质疑、评审智能体补证辩解，FindingLifecycle与EvidenceStore同步更新缺陷状态与证据；
6. 循环结束后ReportWriter Agent输出标准JSON，本地渲染报告文件；
7. 任务状态更新为完成，前端轮询拉取报告、缺陷列表、日志；
8. 可选：新建独立AgentScope Judge会话执行打分，页面展示评分图表。

### 数据流2：CLI命令行启动
参数解析后转发WebTaskManager，复用同一套AgentScope执行逻辑，仅控制台输出进度，无前端交互。

## 2.4 Council与Debate流程架构差异
1. Council固定流程（AgentScope单轮线性会话）
    评审智能体输出缺陷 → Critic一轮质疑 → Lead一次性裁决，会话仅执行一轮交互，无多轮补证、合并逻辑，用作效果基线对照；
2. Debate动态流程（AgentScope多轮循环会话，默认）
    Lead智能体可无限次发起质疑、补证、合并重复缺陷，循环至所有缺陷证据充足无噪音，完整生命周期与证据链管理。

## 2.5 完整技术栈明细
### 2.5.1 运行环境
- Python 3.9+，venv虚拟环境
- 兼容Windows/macOS/Linux

### 2.5.2 核心AI智能体框架
- AgentScope：多智能体调度、消息通信、工具注册、会话循环、智能体生命周期管理

### 2.5.3 大模型与向量服务
- 生成大模型：MiMo（基于AgentScope自定义ModelWrapper接入）
- 向量嵌入模型：text-embedding-v4（独立HTTP调用，不接入AgentScope模型池）

### 2.5.4 Web服务框架
- 后端：FastAPI + uvicorn异步服务
- 前端：原生HTML + CSS + JavaScript（无Vue/React工程化依赖）

### 2.5.5 第三方依赖库
- agentscope：智能体基座核心
- python-dotenv：环境配置读取
- pytest：单元测试
- requests：MiMo、向量模型网络请求
- subprocess：本地Git命令调用
- json/re：数据序列化、文本切片、关键词检索
- argparse：CLI命令行解析
- asyncio：Web异步任务、长轮询

### 2.5.6 文件与存储规范
- 配置文件：.env（MiMo/向量接口密钥）、Markdown（审查规范、企业知识库）
- 任务存储：task_store.json（Web历史任务）
- 输出目录：.review-agent（隔离单次审查所有产物）
- 文件格式：JSON/JSONL（结构化数据、日志）、Markdown（可读报告）

### 2.5.7 架构核心技术特性
1. 基于AgentScope标准化工具注册机制，统一管控Git只读工具调用权限；
2. Skill外部审查规范统一注入所有AgentScope智能体初始化prompt；
3. 多智能体完全依托AgentScope消息总线交互，新增/替换评审角色成本极低；
4. Debate/Council两套流程复用AgentScope会话能力，通过循环策略区分动态/固定流程；
5. FindingLifecycle、EvidenceStore为自研业务模块，与AgentScope会话数据双向绑定；
6. RAG向量检索独立实现，使用text-embedding-v4，支持关键词自动降级；
7. 全链路强约束JSON输出，AgentScope拦截模型返回并校验格式，降低幻觉解析失败；
8. AgentScope会话日志回调统一写入transcript.jsonl，完整可观测、支持页面检索；
9. 双流程基线对比能力，用于自动化AI打分迭代优化；
10. Web异步任务对接AgentScope运行实例，完整可视化任务、报告、评分、日志。

# 三、功能性需求
## 模块1：Web交互与环境基础能力
### 1.1 Web前端页面功能
1. 任务总览页：展示全部历史任务，包含ID、时间、运行模式、总分、状态，支持重启、删除；
2. 新建任务表单：仓库路径、基线/目标commit、PR文档、运行模式、RAG开关、自定义知识库、最大辩论轮次；
3. 实时进度页面：长轮询刷新执行阶段、辩论轮次、缺陷数量，异常完整展示；
4. 审查结果页面：风险分级卡片、单条缺陷完整证据、在线预览report.md、日志关键词检索；
5. AI打分页面：六维度柱状图、完整打分文字、两套流程分数对比；
6. 系统配置页：MiMo接口、text-embedding-v4向量接口、知识库路径配置，密钥仅本地存储。

### 1.2 Web后端接口需求
1. 任务接口：创建任务、查询状态、删除任务、重启历史任务；
2. 文件接口：读取报告、缺陷JSON、日志、知识库、审查规范；
3. 打分接口：独立启动AgentScope Judge智能体执行评估；
4. 配置接口：保存页面基础配置（不存储密钥）；
5. 进度推送接口：长轮询实时返回任务执行进度。

### 1.3 环境管理需求
1. 提供三平台虚拟环境一键初始化脚本；
2. .env配置加载MiMo、向量模型密钥，无密钥自动切换simple离线模式；
3. 完整requirements，包含AgentScope、FastAPI全部依赖，一键安装；
4. pytest覆盖Web接口、AgentScope会话、RAG、工具调用全量单元测试。

### 1.4 CLI备用交互
完整兼容所有启动参数，可独立执行审查与AI打分，仅用于脚本自动化场景。

### 1.5 多运行模式兼容
| 模式 | 运行逻辑 | 使用场景 |
| ---- | ---- | ---- |
| debate（默认） | AgentScope多轮动态辩论会话 | 日常正式代码审查 |
| council | AgentScope单轮固定线性会话 | 基线效果对比、教学演示 |
| simple | 本地离线无模型，不启动AgentScope大模型会话 | 无密钥本地演示调试 |
| agentic | AgentScope全局单智能体ReAct实验会话 | 技术方案验证迭代 |

## 模块2：AgentScope工具调用模块
所有工具通过agentscope.register_tool注册，仅开放只读权限：
1. git_diff：读取两段commit之间完整代码变更；
2. changed_files：获取本次所有修改文件路径；
3. read_file_context：读取指定文件完整上下文；
4. search_code：仓库内关键字、函数检索；
5. secret_scan：扫描代码明文密钥、token、密码；
6. run_tests：仅用户传入自定义测试命令才可执行，无入参禁止调用。

## 模块3：Skill规范加载模块
1. 读取本地Markdown审查规范，包含风险等级、缺陷JSON格式、各类代码审查要点；
2. 程序加载后注入所有AgentScope智能体初始prompt；
3. 修改规范文件无需重启Web服务，自动热加载。

## 模块4：企业RAG知识库模块
1. 读取指定目录Markdown规范（安全基线、支付规范、测试要求、事故案例）；
2. 自动文档切片、文本清洗；
3. 向量阶段独立调用text-embedding-v4，无向量密钥自动降级关键词正则检索；
4. 三层检索逻辑：审查前置注入全局上下文、缺陷匹配规范证据、独立规范智能体主动检索；
5. Web页面提供RAG开关，关闭后可做消融对比实验。

## 模块5：基于AgentScope的多智能体协作模块
全部智能体继承agentscope.AgentBase，统一接入全局MiMo模型池：
1. 专业评审智能体组：安全、正确性、测试、可维护性、企业规范审查Agent；
2. Critic质检智能体：反向校验缺陷证据、重复、风险夸大问题；
3. Lead辩论控制智能体：通过AgentScope循环下发质疑、补证、合并、驳回、确认等动作；
4. ReportWriter输出智能体：强制输出固定结构JSON，禁止自由文本；
5. AI Judge评估智能体：独立会话执行六维度标准化打分。

## 模块6：Debate辩论循环业务能力
1. FindingLifecycle：缺陷完整状态流转：候选→被质疑→接受/驳回/降级，全程记录变更；
2. EvidenceStore：每条缺陷绑定代码文件、行数、上下文、质疑、辩解、企业规范引用完整证据链；
3. AgentScope会话多轮循环，Lead动态决策下一步操作，直至无重复、证据充足后结束；
4. Council模式仅一轮质疑一轮裁决，无多轮迭代逻辑。

## 模块7：标准化报告输出
1. 所有AgentScope智能体输出强制JSON，程序捕获并修复markdown代码块、字段缺失等格式异常；
2. 统一输出至.review-agent目录：
    - report.md：程序模板渲染可读报告；
    - findings.json：结构化存储缺陷、生命周期、证据链；
    - judge_input.json：AI打分专用标准化输入；
    - transcript.jsonl：AgentScope全会话日志；
    - judge.json/judge.md：打分结果文件；
3. 报告每条缺陷附带匹配企业规范索引，Web页面可跳转对应规范片段。

## 模块8：AI Judge评估功能
1. 独立创建AgentScope Judge会话，仅读取judge_input.json，不受报告文笔影响；
2. 六大固定评分维度：关键风险覆盖、证据质量、风险准确度、重复噪音控制、修复可执行度、报告清晰度；
3. 输出结构化分数与文字评价，Web端图表可视化；
4. 仅用作不同流程横向对比指标，不作为代码合并唯一判定依据。

## 模块9：全链路日志可观测
1. 接入AgentScope日志回调，所有智能体消息、工具调用、模型请求全部写入transcript.jsonl；
2. Web页面支持关键词检索日志，快速定位辩论、合并、RAG检索等关键步骤；
3. 离线、模型超时、向量降级等异常单独标记日志，方便调试。

# 四、非功能性需求
## 4.1 性能需求
1. simple离线模式：100行内代码变更10秒内完成；
2. debate完整审查流程：常规业务代码变更总耗时≤5分钟；
3. text-embedding-v4单条向量检索响应≤2秒；
4. Web长轮询进度刷新延迟≤1秒；
5. Web最多同时排队3个任务，超出提示排队等待；
6. 单次审查日志独立隔离，不与其他任务日志混淆。

## 4.2 兼容性需求
1. Web服务全平台Windows/macOS/Linux兼容；
2. Python3.9及以上版本；
3. 支持Git标准commit、分支、HEAD相对引用；
4. MiMo、text-embedding-v4兼容标准HTTP接口，支持私有化模型地址配置；
5. 任意模型密钥缺失自动降级simple离线模式，页面清晰提示离线状态。

## 4.3 安全需求
1. AgentScope注册工具全部只读，禁止文件修改、删除、写入；
2. run_tests仅用户手动传入命令才可执行，默认禁止；
3. MiMo、向量密钥仅存储本地.env，不传输前端、不打印日志；
4. 敏感密钥扫描结果页面脱敏，不展示完整明文；
5. Web服务仅本地127.0.0.1监听，禁止外网端口暴露。

## 4.4 可维护性需求
1. 代码分层清晰：Web接口层、AgentScope智能体层、工具层、RAG层、报告渲染层完全解耦；
2. 提示词、审查规范、参数全部外部文件配置，无硬编码；
3. 单元测试覆盖Web接口、AgentScope会话、工具调用、RAG降级、JSON解析；
4. 目录标准化：前端页面、知识库、demo代码、测试、运行输出目录分离。

## 4.5 易用性需求
1. 完整README：Web启动、环境部署、页面功能、命令行、输出文件说明；
2. 内置payment风险demo，页面一键加载demo参数快速复现流程；
3. 页面清晰区分在线MiMo模式、离线simple模式；
4. 友好页面报错，区分仓库错误、模型超时、规范缺失、RAG失败等异常。

# 五、数据需求
## 5.1 输入数据
1. Git仓库代码、代码diff变更；
2. PR描述Markdown文件；
3. 企业规范知识库Markdown；
4. .env配置：MiMo接口地址、向量接口地址、密钥；
5. Web表单参数 / CLI命令行参数。

## 5.2 中间存储数据
1. task_store.json：Web历史任务状态；
2. 知识库文本切片、text-embedding-v4向量缓存；
3. transcript.jsonl：AgentScope全会话日志；
4. findings.json、judge_input.json：结构化缺陷与打分中间文件。

## 5.3 输出数据
1. report.md可读审查报告；
2. findings.json结构化缺陷数据；
3. judge.json、judge.md AI打分结果；
4. transcript.jsonl完整智能体执行日志；
5. task_store.json持久化Web任务记录。

# 六、约束与边界需求
1. Web仅本地单机运行，不支持多用户、分布式、外网访问；
2. AI Judge仅用于council/debate流程对比，不可作为代码合并唯一判定标准；
3. RAG仅支持本地Markdown知识库，不对接远程知识库接口；
4. 工具仅适配Git，不支持SVN等其他版本管理工具；
5. 单次任务仅处理单个仓库单次代码变更，不支持多仓库并行；
6. 生成模型统一MiMo、向量固定text-embedding-v4，不可随意替换；
7. 多智能体调度、消息、工具完全基于AgentScope框架，不自研会话调度；
8. text-embedding-v4向量模块独立开发，不接入AgentScope模型池；
9. AgentScope仅负责智能体交互，RAG检索、证据存储、报告渲染、任务管理为自研业务模块。

# 七、二期拓展优化需求
1. 对接Semgrep/AST静态分析，补充代码深层缺陷识别；
2. AgentScope批量合并重复辩论动作，减少MiMo调用次数，降低token消耗；
3. 搭建人工标注数据集，校准AI Judge打分标准；
4. 缓存text-embedding-v4向量与高频prompt，加速审查速度；
5. Web页面增加报告PDF、缺陷Excel导出功能；
6. 实现批量多PR一次性审查任务；
7. 支持多套MiMo模型密钥快速切换配置；
8. 接入简单向量库（Chroma）持久化知识库向量，无需每次启动重算。