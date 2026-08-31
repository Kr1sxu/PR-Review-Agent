# RAG 模块 — PR-Review Agent

本地 Markdown 知识库检索，支持语义切片和向量搜索。

## 模块清单

| 文件 | 功能 |
|------|------|
| chunker.py | Markdown 语义切片，按标题/段落分割，支持配置大小和重叠 |
| vector_store.py | 内存向量缓存，余弦相似度 Top-K，JSON 持久化 |
| retriever.py | 统一检索入口，失败时优雅降级 |

## 使用示例

```python
from src.rag.retriever import RAGRetriever
from src.models.embedding import create_embedding_model

model = create_embedding_model(api_url="...", api_key="...", dimensions=1024)
retriever = RAGRetriever(
    embedding_model=model,
    knowledge_base_path="./knowledge_base",
    chunk_size=512,
    chunk_overlap=64,
    top_k=5,
    similarity_threshold=0.7,
    cache_path="./output/.vector_cache",
)
retriever.initialize()

# 搜索
results = retriever.retrieve("SQL 注入防护")
# [{text, source_file, section_title, score}, ...]

# 获取格式化上下文（用于注入 Prompt）
context = retriever.get_context_string("支付幂等性")
```

## 设计说明
- 切片策略：先按 `#` 标题分割，大段落再按段落分割
- 向量存储：运行时内存缓存，可选 JSON 文件持久化
- 降级机制：失败时返回空结果，不阻塞审查流程
