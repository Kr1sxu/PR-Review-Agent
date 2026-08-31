path = r"D:\Users\18532\Desktop\LXH\Project\PR-Review Agent\record.md"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

note = """

### 阶段三补充：AgentScope 原生重构

安装 `agentscope==2.0.5` 后，对模型封装层进行了全面重构：

**重构变更：**
- `mimo_wrapper.py` — 从自建基类改为继承 `ChatModelBase`（`agentscope.model._base`）
  - 使用 `OpenAICredential` 管理 API 凭证
  - `_call_api` 改为 `async` 方法，返回标准 `ChatResponse`（含 `TextBlock`）
  - `__call__` 由基类统一托管（含重试逻辑）
  - 新增 `MiMoParameters`（Pydantic BaseModel）替代裸参数
  - 新增 `create_mimo_model()` 工厂函数
- `embedding.py` — 从独立 HTTP 客户端改为继承 `EmbeddingModelBase`（`agentscope.embedding`）
  - `_call_api` 改为 `async` 方法，返回标准 `EmbeddingResponse`
  - 基类自动处理分批和重试
  - 新增 `create_embedding_model()` 工厂函数
- 测试全部适配 AgentScope v2 类型（`Msg`、`TextBlock`、`ChatResponse`）
- **29 个测试全部通过**，无降级逻辑
"""

content += note

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("Updated record.md")
