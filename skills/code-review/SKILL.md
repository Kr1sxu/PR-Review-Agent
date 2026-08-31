# Code Review Skill

> 系统化代码审查指南，用于指导 PR-Review Agent 进行高质量的多维度代码审查。

---

## 1. 审查清单（Review Checklist）

审查时必须覆盖以下 **6 个维度**，每个维度包含若干检查项。

### 1.1 安全性（Security）

| # | 检查项 | 说明 |
|---|--------|------|
| S1 | 注入攻击 | SQL 注入、命令注入、XSS、路径遍历、LDAP/XML/SSRF 注入 |
| S2 | 认证与授权 | 缺失认证、权限提升、JWT/Session 处理不当、硬编码凭证 |
| S3 | 敏感数据泄露 | 日志中打印密码/Token、明文存储、git 中残留密钥 |
| S4 | 加密安全 | 使用弱算法（MD5/SHA1）、ECB 模式、硬编码 IV/Salt |
| S5 | 依赖安全 | 已知漏洞的第三方库、过时的依赖版本 |
| S6 | 输入校验 | 未校验用户输入、缺失类型/长度/范围检查 |
| S7 | 反序列化 | 不安全的 pickle/yaml.load、eval/exec 调用 |

### 1.2 准确性（Correctness）

| # | 检查项 | 说明 |
|---|--------|------|
| C1 | 业务逻辑 | 条件判断错误、计算偏差、状态机转换遗漏 |
| C2 | 边界条件 | 数组越界、空值处理、整数溢出、浮点精度 |
| C3 | 错误处理 | 裸 except、吞异常、未处理的错误码、缺少 finally 清理 |
| C4 | 并发安全 | 竞态条件、死锁风险、共享状态无保护 |
| C5 | 资源管理 | 文件/连接未关闭、内存泄漏、未使用 context manager |
| C6 | API 契约 | 返回值类型不一致、缺少参数校验、违反接口约定 |

### 1.3 性能（Performance）

| # | 检查项 | 说明 |
|---|--------|------|
| P1 | 算法复杂度 | O(n²) 可优化为 O(n log n)、不必要的嵌套循环 |
| P2 | 数据库 | N+1 查询、缺少索引、全表扫描、大事务 |
| P3 | 缓存 | 热数据未缓存、缓存穿透/雪崩、无 TTL |
| P4 | I/O 效率 | 同步阻塞调用、未批量处理、大文件一次性读取 |
| P5 | 内存使用 | 大对象未释放、循环引用、不必要的深拷贝 |

### 1.4 可维护性（Maintainability）

| # | 检查项 | 说明 |
|---|--------|------|
| M1 | 代码结构 | 函数过长（>50行）、类过大、圈复杂度 > 10 |
| M2 | 命名规范 | 变量/函数名含义不清、缩写不一致、魔法数字 |
| M3 | 重复代码 | 相似逻辑未抽取、可复用的工具函数未抽象 |
| M4 | 文档注释 | 公共 API 无 docstring、复杂逻辑无注释、TODO/FIXME 残留 |
| M5 | 耦合度 | 模块间循环依赖、过度耦合、违反单一职责 |
| M6 | 向后兼容 | 破坏性变更未标记、缺少迁移路径 |

### 1.5 测试（Testing）

| # | 检查项 | 说明 |
|---|--------|------|
| T1 | 覆盖率 | 新增代码无对应测试、核心路径未覆盖 |
| T2 | 断言质量 | 仅 assert True、缺少边界值测试、断言过于宽松 |
| T3 | 测试隔离 | 测试间有顺序依赖、共享可变状态、未 mock 外部依赖 |
| T4 | 边界测试 | 缺少空值/零值/极大值/极小值测试用例 |
| T5 | 异常路径 | 未测试错误处理分支、未验证异常消息 |

### 1.6 规范合规（Compliance）

| # | 检查项 | 说明 |
|---|--------|------|
| L1 | 编码规范 | PEP8/ESLint 违规、格式不一致 |
| L2 | 日志规范 | 日志级别不当、缺少关键操作日志、日志格式不统一 |
| L3 | API 设计 | RESTful 规范、错误码体系、版本管理 |
| L4 | 国际化 | 硬编码用户可见字符串、时区/编码处理 |

---

## 2. 输出格式（Output Schema）

每个发现的问题必须以 **结构化 JSON** 输出，包含以下字段：

```json
{
  "id": "SEC-001",
  "category": "security",
  "severity": "P0",
  "title": "SQL 注入：用户输入直接拼接到查询语句",
  "description": "在 payment.py 第 42 行，用户的 card_number 参数未经转义直接拼接到 SQL 语句中，攻击者可构造恶意输入获取任意数据。",
  "file_path": "src/payment.py",
  "line_range": "42-45",
  "evidence": "query = f\"SELECT * FROM payments WHERE card='{card_number}'\"",
  "impact": "攻击者可通过注入获取全部支付记录和用户敏感信息",
  "suggestion": "使用参数化查询：cursor.execute(\"SELECT * FROM payments WHERE card=%s\", (card_number,))",
  "confidence": 0.95,
  "spec_reference": "OWASP Top 10 A03:2021 - Injection"
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 唯一标识，格式：`{分类}-{序号}`，如 `SEC-001` |
| `category` | string | 是 | 分类：`security` / `correctness` / `performance` / `maintainability` / `testing` / `compliance` |
| `severity` | string | 是 | 严重级别：`P0` / `P1` / `P2` / `P3` |
| `title` | string | 是 | 一句话标题，格式：`问题类型：具体描述` |
| `description` | string | 是 | 详细描述，说明问题的原因、触发条件和影响范围 |
| `file_path` | string | 是 | 文件相对路径 |
| `line_range` | string | 是 | 行号范围，如 `42` 或 `42-45` |
| `evidence` | string | 是 | 问题代码片段（不超过 500 字符） |
| `impact` | string | 是 | 影响说明：该问题会导致什么后果 |
| `suggestion` | string | 是 | 具体的修复建议，最好包含代码示例 |
| `confidence` | float | 是 | 置信度 0.0-1.0 |
| `spec_reference` | string | 否 | 相关规范/标准引用 |

### 严重级别定义

| 级别 | 含义 | 示例 |
|------|------|------|
| **P0** | **致命** — 必须立即修复 | SQL 注入、硬编码密钥、认证绕过、数据泄露 |
| **P1** | **严重** — 合并前必须修复 | 未处理异常、资源泄漏、竞态条件、逻辑错误 |
| **P2** | **一般** — 建议修复 | 代码重复、命名不规范、缺少注释、性能隐患 |
| **P3** | **轻微** — 可选修复 | 格式问题、风格建议、小的代码改进 |

---

## 3. 裁决规则（Decision Rules）

根据发现的问题严重级别，给出明确的审查结论：

```
┌─────────────────────────────────────────────────┐
│            裁决决策树                            │
├─────────────────────────────────────────────────┤
│ 存在 P0 问题？                                  │
│   └─ 是 → ❌ REQUEST_CHANGES（拒绝合并）        │
│   └─ 否 → 继续                                  │
│                                                 │
│ 存在 P1 问题？                                  │
│   └─ 是 → ❌ REQUEST_CHANGES（拒绝合并）        │
│   └─ 否 → 继续                                  │
│                                                 │
│ 存在 P2 问题？                                  │
│   └─ 是 → 💬 COMMENT（评论，不阻止合并）        │
│   └─ 否 → 继续                                  │
│                                                 │
│ 存在 P3 问题？                                  │
│   └─ 是 → 💬 COMMENT（评论，不阻止合并）        │
│   └─ 否 → 继续                                  │
│                                                 │
│ 无任何问题                                      │
│   └─ ✅ APPROVE（批准合并）                      │
└─────────────────────────────────────────────────┘
```

### 裁决输出格式

```json
{
  "verdict": "request_changes | comment | approve",
  "reason": "发现 1 个 P0 和 2 个 P1 问题，需要修复后重新提交",
  "summary": {
    "P0": 1,
    "P1": 2,
    "P2": 3,
    "P3": 1,
    "total": 7
  }
}
```

---

## 4. 常见反模式（Anti-Patterns）

审查时特别关注以下常见问题模式：

### 4.1 安全反模式

```python
# ❌ 反模式：SQL 拼接
query = f"SELECT * FROM users WHERE id={user_id}"

# ❌ 反模式：硬编码密钥
API_KEY = "sk-1234567890abcdef"

# ❌ 反模式：eval 执行用户输入
result = eval(user_input)

# ❌ 反模式：禁用 SSL 验证
requests.get(url, verify=False)

# ❌ 反模式：明文存储密码
password = hashlib.md5(raw_password.encode()).hexdigest()
```

### 4.2 错误处理反模式

```python
# ❌ 反模式：裸 except 吞掉所有异常
try:
    do_something()
except:
    pass

# ❌ 反模式：异常处理中使用 assert
try:
    result = api_call()
except Exception:
    assert False, "API call failed"  # 测试中 assert 会被优化掉

# ❌ 反模式：打印后继续执行
try:
    risky_operation()
except Exception as e:
    print(f"Error: {e}")  # 应该 log 或 raise
```

### 4.3 测试反模式

```python
# ❌ 反模式：无断言的测试
def test_payment():
    process_payment(100)  # 没有 assert，无法验证结果

# ❌ 反模式：测试依赖执行顺序
def test_create_user():
    global user_id
    user_id = create_user("test")

def test_delete_user():
    delete_user(user_id)  # 依赖上一个测试

# ❌ 反模式：过于宽泛的断言
def test_result():
    assert result is not None  # 什么都检查不了
```

### 4.4 设计反模式

```python
# ❌ 反模式：上帝函数（一个函数做太多事）
def process_order(order):
    validate(order)        # 校验
    calculate_tax(order)   # 计算税
    charge_payment(order)  # 扣款
    send_email(order)      # 发邮件
    update_inventory(order)# 更新库存
    log_audit(order)       # 审计日志
    # 一个函数 200+ 行...

# ❌ 反模式：魔法数字
if status == 3:  # 3 代表什么？
    retry_after = 300  # 为什么是 300？

# ❌ 反模式：循环导入
# a.py: from b import func_b
# b.py: from a import func_a
```

---

## 5. 审查辅助工具（Review Tools）

审查过程中通过以下**已注册工具**辅助分析。工具名称和参数必须严格匹配，直接调用即可。

### 5.1 `git_ops` — Git 操作

对仓库执行只读 Git 操作，返回 diff、文件列表、文件内容或提交信息。

**参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `action` | string | 是 | — | 操作类型：`diff` / `list_files` / `file_content` / `commit_message` |
| `base_ref` | string | 否 | — | 基准 ref（diff、list_files 需要） |
| `target_ref` | string | 否 | — | 目标 ref（diff、list_files 需要） |
| `commit` | string | 否 | — | 提交 ref（file_content、commit_message 需要） |
| `file_path` | string | 否 | — | 文件路径（file_content 需要） |

**调用示例：**

```json
// 查看变更文件列表
{ "action": "list_files", "base_ref": "main", "target_ref": "feature-branch" }

// 查看代码 diff
{ "action": "diff", "base_ref": "HEAD~1", "target_ref": "HEAD" }

// 查看某次提交中某文件的内容
{ "action": "file_content", "commit": "HEAD", "file_path": "src/payment.py" }

// 查看提交信息
{ "action": "commit_message", "commit": "HEAD" }
```

### 5.2 `search_code` — 代码搜索

在仓库文件中按关键词或正则表达式搜索，返回匹配的文件、行号和内容。

**参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `keyword` | string | 是 | — | 搜索关键词或正则表达式 |
| `directory` | string | 否 | `"."` | 搜索目录 |
| `file_pattern` | string | 否 | `""` | 文件后缀过滤，如 `".py"` |
| `max_results` | int | 否 | `50` | 最大返回条数 |

**调用示例：**

```json
// 搜索 TODO/FIXME/HACK 残留
{ "keyword": "TODO|FIXME|HACK|XXX", "file_pattern": ".py" }

// 搜索硬编码密钥
{ "keyword": "password\\s*=\\s*['"]", "file_pattern": ".py" }
{ "keyword": "api_key\\s*=\\s*['"]", "file_pattern": ".py" }
{ "keyword": "secret\\s*=\\s*['"]", "file_pattern": ".py" }

// 搜索不安全函数调用
{ "keyword": "eval\\s*\\(", "file_pattern": ".py" }
{ "keyword": "exec\\s*\\(", "file_pattern": ".py" }
{ "keyword": "pickle\\.load", "file_pattern": ".py" }

// 搜索裸 except
{ "keyword": "except:", "file_pattern": ".py" }

// 搜索 print 调试语句（排除测试文件）
{ "keyword": "print\\(", "file_pattern": ".py", "directory": "src" }
```

### 5.3 `risk_scan` — 风险模式扫描

扫描代码中的公司策略风险模式，包括：SQL 注入、Webhook 签名缺失、敏感信息日志泄露、支付流程未 fail-closed、缺少测试、幂等性问题。返回结构化的风险发现（含文件、行号、严重级别）。

**参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `directory` | string | 否 | `"."` | 扫描目录 |
| `risk_categories` | list[string] | 否 | 全部 | 指定风险类别 |
| `file_pattern` | string | 否 | `""` | 文件后缀过滤 |

**可选风险类别：** `sql_injection`, `webhook_signing`, `sensitive_logging`, `payment_fail_closed`, `missing_tests`, `idempotency`

**调用示例：**

```json
// 扫描全部风险类别
{ "directory": "src", "file_pattern": ".py" }

// 仅扫描 SQL 注入和敏感日志
{ "directory": "src", "risk_categories": ["sql_injection", "sensitive_logging"] }
```

### 5.4 `read_file` — 读取文件

读取指定文件的完整内容，用于审查具体文件的实现细节。

**参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `path` | string | 是 | — | 文件路径 |

**调用示例：**

```json
{ "path": "src/payment.py" }
```

### 5.5 `run_tests` — 运行测试（默认禁用）

> ⚠️ 此工具默认禁用（`enabled=False`），需管理员显式启用后方可使用。启用后还受白名单限制（`allowed_commands`），只有在白名单中的命令才能执行。

执行测试命令并返回结果。

**参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `command` | string | 是 | — | 测试命令 |
| `cwd` | string | 否 | `"."` | 工作目录 |
| `timeout` | int | 否 | `60` | 超时秒数 |

**调用示例：**

```json
{ "command": "pytest --tb=short", "timeout": 120 }
```

### 5.6 注意事项

- **Git 操作**通过 `git_ops` 工具执行，支持查看 diff、变更文件列表、文件内容和提交信息。
- 复杂度分析（radon）、依赖安全检查（safety/pip-audit）等未注册为工具，如需要可建议用户手动执行。
- 优先使用 `risk_scan` 进行安全扫描，它内置了 SQL 注入、敏感日志、支付安全等检测规则，比手动搜索更全面。

## 6. 审查工作流（Review Workflow）

按照以下 **7 步流程** 进行系统化审查：

```
┌──────────────────────────────────────────────────────────────┐
│                    代码审查工作流                              │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Step 1  理解上下文                                          │
│    ├─ 阅读 PR 描述，理解变更目的                              │
│    ├─ 使用 git_ops(action="list_files") 查看变更文件列表，评估影响范围                          │
│    └─ 了解相关模块的职责和依赖关系                            │
│                          ↓                                   │
│  Step 2  运行代码                                            │
│    ├─ 确认代码可正常运行（无语法错误）                        │
│    ├─ 运行现有测试确认无回归                                  │
│    └─ 观察实际行为是否符合预期                                │
│                          ↓                                   │
│  Step 3  顶层阅读                                            │
│    ├─ 快速浏览全部变更，建立整体认知                          │
│    ├─ 识别变更的核心逻辑和关键路径                            │
│    └─ 标记需要深入审查的区域                                  │
│                          ↓                                   │
│  Step 4  检查测试                                            │
│    ├─ 新增代码是否有对应测试                                  │
│    ├─ 测试是否覆盖了正常路径和异常路径                        │
│    ├─ 断言是否充分且具体                                      │
│    └─ 边界条件是否已测试                                      │
│                          ↓                                   │
│  Step 5  安全扫描                                            │
│    ├─ 检查注入风险（SQL/命令/XSS）                           │
│    ├─ 检查敏感数据处理（加密、存储、传输）                    │
│    ├─ 检查认证授权逻辑                                        │
│    └─ 使用 risk_scan 扫描风险模式，用 search_code 搜索已知反模式                            │
│                          ↓                                   │
│  Step 6  手动审查                                            │
│    ├─ 逐行审查关键变更                                        │
│    ├─ 检查逻辑正确性和边界条件                                │
│    ├─ 评估性能影响                                            │
│    ├─ 检查代码可维护性（命名、结构、注释）                    │
│    └─ 对照审查清单逐项检查                                    │
│                          ↓                                   │
│  Step 7  撰写反馈                                            │
│    ├─ 按严重级别组织发现（P0 → P3）                          │
│    ├─ 每个发现附带代码证据和修复建议                          │
│    ├─ 给出裁决结论（approve / comment / request_changes）    │
│    └─ 总体评价和改进建议                                      │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 工作流检查清单

每一步完成后，确认以下事项：

- [ ] **Step 1**：能用一句话描述这次变更的目的
- [ ] **Step 2**：代码可正常运行，现有测试全部通过
- [ ] **Step 3**：识别出了变更的核心模块和影响范围
- [ ] **Step 4**：测试覆盖率充分，关键路径已覆盖
- [ ] **Step 5**：无高危安全漏洞（P0/P1 级别）
- [ ] **Step 6**：逐行审查完成，所有检查项已过一遍
- [ ] **Step 7**：反馈结构清晰，裁决结论明确

---

## 附录：裁决决策速查表

| 情况 | 裁决 |
|------|------|
| 有任何 P0 问题 | `request_changes` |
| 有任何 P1 问题 | `request_changes` |
| 仅有 P2 问题 | `comment` |
| 仅有 P3 问题 | `comment` |
| 无任何问题 | `approve` |
| 安全漏洞（无论级别） | 至少 `comment`，高危必须 `request_changes` |
| 缺少测试的新功能 | `comment`（附带测试建议） |
| 破坏性变更无迁移方案 | `request_changes` |