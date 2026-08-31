# 模型模块 — PR-Review Agent

PR-Review Agent 的模型接口封装层，基于 AgentScope v2 标准实现。

## 模块清单

| 文件 | 功能 | 说明 |
|------|------|------|
| mimo_wrapper.py | ChatModelBase | MiMo 大模型封装，含 HTTP 请求、超时重试、JSON 校验、离线降级 |
| embedding.py | EmbeddingModelBase | Embedding 向量模型封装，含单条/批量处理、相似度计算、离线降级 |

## 使用示例

### MiMo 模型调用
```python
from src.models.mimo_wrapper import create_mimo_model
from src.core.config_loader import get_config

config = get_config()
mimo_cfg = config.get_model_config("mimo")

# 创建模型实例（自动继承 AgentScope ChatModelBase）
model = create_mimo_model(
    api_url=mimo_cfg.get("api_url", ""),
    api_key=mimo_cfg.get("api_key", ""),
    model_name=mimo_cfg.get("model_name", "mimo"),
)

# 异步调用（AgentScope 标准接口）
import asyncio
from agentscope.message._base import Msg
messages = [Msg(role="user", content="你好，请分析")]
response = asyncio.get_event_loop().run_until_complete(model("mimo", messages))

# 获取文本 / JSON
text = model.get_text(response)
data = model.get_json(response)
```

### Embedding 向量调用
```python
from src.models.embedding import create_embedding_model

client = create_embedding_model(
    api_url="https://api.example.com/v1/embeddings",
    api_key="sk-xxx",
    dimensions=1024,
)

# 同步调用接口
vec = client.embed_single("支付安全规范")
vecs = client.embed_batch(["规范一", "规范二", "规范三"])
score = MiMoEmbeddingModel.similarity(vec_a, vec_b)
```

## 设计原则
- **AgentScope 原生兼容**：继承 ChatModelBase / EmbeddingModelBase，支持 AgentScope 全局模型注册
- **离线降级保障**：密钥缺失时自动切换离线模式
- **工厂便捷创建**：create_mimo_model() / create_embedding_model() 一行代码创建实例
