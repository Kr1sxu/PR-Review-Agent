# 记忆系统重构记录：PostgreSQL + pgvector

> 日期：2026-08-13
> 变更类型：架构重构
> 影响范围：存储层、RAG 向量检索、数据库连接

---

## 一、重构背景

原系统使用纯内存 + JSON 文件作为存储方案：
- **EvidenceStore**：审查数据存在 Python 对象中，审查结束写入 JSON 文件
- **VectorStore**：RAG 向量存在 Python list 中，可选持久化到 JSON
- **无长期记忆**：每次审查都是独立运行的，无法跨任务检索历史经验

重构目标：引入 PostgreSQL + pgvector，实现：
1. 审查数据实时持久化到数据库
2. RAG 向量存储从内存迁移到 pgvector
3. 为长期记忆（跨任务检索）打下基础

---

## 二、新增文件

| 文件 | 说明 |
|---|---|
| `docker-compose.yml` | PostgreSQL + pgvector 容器配置 |
| `scripts/init.sql` | 数据库表结构初始化脚本（8 张表） |
| `src/core/database.py` | 异步数据库连接池管理（asyncpg） |
| `docs/memory-system-refactor.md` | 本文档 |

---

## 三、修改文件

| 文件 | 变更说明 |
|---|---|
| `src/rag/vector_store.py` | **重写**：从纯内存 list 改为 pgvector 表存储，保留原有 API 接口 |
| `src/rag/retriever.py` | **适配**：改用异步向量检索方法 |
| `src/flows/evidence_store.py` | **重写**：数据写入改为异步持久化到 PostgreSQL，新增长期记忆查询方法 |
| `src/main.py` | **新增**：CLI 启动时初始化数据库连接 |
| `src/web_app.py` | **新增**：FastAPI lifespan 管理数据库连接生命周期 |
| `config/settings.yaml` | **新增**：database 配置段 |
| `.env` | **新增**：DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD |
| `requirements.txt` | **新增**：asyncpg>=0.29.0 |

---

## 四、数据库表结构

### 4.1 审查记录（长期记忆）
```sql
review_history (task_id, findings_count, severity_dist, created_at)
```

### 4.2 Findings
```sql
findings (task_id, finding_id, category, severity, title, description,
          file_path, line_range, evidence, suggestion, confidence,
          spec_reference, sources)
```
索引：task_id / severity / category

### 4.3 Policy References
```sql
policy_references (task_id, policy_id, policy_area, policy_label,
                   rule_text, matched_finding_ids, source)
```

### 4.4 Challenges（Critic 质疑）
```sql
challenges (task_id, challenge_id, finding_id, challenger, action,
            reason, new_severity, merge_target_id)
```

### 4.5 Decisions（Lead Controller 裁决）
```sql
decisions (task_id, decision_id, finding_id, action, reason,
           new_severity, merge_target_id)
```

### 4.6 Debate History（辩论轮次）
```sql
debate_history (task_id, round_number, lead_action, target_finding_id,
                actor, result_summary, consensus_score, findings_count)
```

### 4.7 RAG 向量（pgvector）
```sql
rag_vectors (chunk_text, source_file, section_title, chunk_index,
             embedding VECTOR(1024))
```
索引：IVFFlat 余弦相似度（lists=16）

### 4.8 历史审查向量（长期记忆）
```sql
review_vectors (task_id, summary_text, embedding VECTOR(1024))
```
索引：IVFFlat 余弦相似度（lists=8）

---

## 五、EvidenceStore 新增的长期记忆 API

```python
# 检索历史上最相似的审查
await EvidenceStore.query_similar_reviews(embedding, top_k=5)

# 查询某类别的历史 findings
await EvidenceStore.query_findings_by_category("sql_injection", limit=20)

# 查询高频问题模式
await EvidenceStore.query_high_frequency_patterns(min_count=3)
```

---

## 六、使用方式

### 启动数据库
```bash
docker compose up -d
```

### 启动应用
```bash
# CLI
python -m src.main --repo ./demo/payment_repo

# Web
uvicorn src.web_app:app --reload
```

数据库会在首次启动时自动连接，无需手动建表（init.sql 由 Docker 自动执行）。

---

## 七、兼容性说明

- EvidenceStore 的 to_dict() 接口保持不变，report_writer.py 和 judge_runner.py 无需修改
- VectorStore 的 add() / search() 同步接口保留，内部转异步
- JSON 文件输出仍然保留（save_json），同时异步写入 PostgreSQL
- 如果 PostgreSQL 不可用，系统降级为无持久化模式，审查流程不受影响
