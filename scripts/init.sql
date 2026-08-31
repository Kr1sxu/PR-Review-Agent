-- PR-Review Agent 数据库初始化脚本
-- PostgreSQL + pgvector

CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- 1. 审查记录（长期记忆：每次审查的摘要）
-- ============================================================
CREATE TABLE IF NOT EXISTS review_history (
    id              SERIAL PRIMARY KEY,
    task_id         VARCHAR(128) UNIQUE NOT NULL,
    repo_name       VARCHAR(256) DEFAULT '',
    flow_mode       VARCHAR(32)  DEFAULT '',
    findings_count  INT          DEFAULT 0,
    severity_dist   JSONB        DEFAULT '{}',
    duration_sec    FLOAT        DEFAULT 0.0,
    created_at      TIMESTAMPTZ  DEFAULT NOW()
);

-- ============================================================
-- 2. Findings（审查发现的问题）
-- ============================================================
CREATE TABLE IF NOT EXISTS findings (
    id              SERIAL PRIMARY KEY,
    task_id         VARCHAR(128) NOT NULL,
    finding_id      VARCHAR(64)  NOT NULL,
    category        VARCHAR(64)  DEFAULT '',
    severity        VARCHAR(16)  DEFAULT 'medium',
    title           TEXT         DEFAULT '',
    description     TEXT         DEFAULT '',
    file_path       TEXT         DEFAULT '',
    line_range      VARCHAR(64)  DEFAULT '',
    evidence        TEXT         DEFAULT '',
    suggestion      TEXT         DEFAULT '',
    confidence      FLOAT        DEFAULT 0.5,
    spec_reference  TEXT         DEFAULT '',
    sources         JSONB        DEFAULT '[]',
    created_at      TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_findings_task ON findings(task_id);
CREATE INDEX IF NOT EXISTS idx_findings_severity ON findings(severity);
CREATE INDEX IF NOT EXISTS idx_findings_category ON findings(category);

-- ============================================================
-- 3. Policy References（公司规范引用）
-- ============================================================
CREATE TABLE IF NOT EXISTS policy_references (
    id                   SERIAL PRIMARY KEY,
    task_id              VARCHAR(128) NOT NULL,
    policy_id            VARCHAR(128) DEFAULT '',
    policy_area          VARCHAR(128) DEFAULT '',
    policy_label         TEXT         DEFAULT '',
    rule_text            TEXT         DEFAULT '',
    matched_finding_ids  JSONB        DEFAULT '[]',
    source               TEXT         DEFAULT '',
    created_at           TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_policy_refs_task ON policy_references(task_id);

-- ============================================================
-- 4. Challenges（Critic 质疑记录）
-- ============================================================
CREATE TABLE IF NOT EXISTS challenges (
    id              SERIAL PRIMARY KEY,
    task_id         VARCHAR(128) NOT NULL,
    challenge_id    VARCHAR(64)  NOT NULL,
    finding_id      VARCHAR(64)  NOT NULL,
    challenger      VARCHAR(64)  DEFAULT '',
    action          VARCHAR(32)  DEFAULT '',
    reason          TEXT         DEFAULT '',
    new_severity    VARCHAR(16)  DEFAULT '',
    merge_target_id VARCHAR(64)  DEFAULT '',
    created_at      TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_challenges_task ON challenges(task_id);

-- ============================================================
-- 5. Decisions（Lead Controller 裁决记录）
-- ============================================================
CREATE TABLE IF NOT EXISTS decisions (
    id              SERIAL PRIMARY KEY,
    task_id         VARCHAR(128) NOT NULL,
    decision_id     VARCHAR(64)  NOT NULL,
    finding_id      VARCHAR(64)  NOT NULL,
    action          VARCHAR(32)  DEFAULT '',
    reason          TEXT         DEFAULT '',
    new_severity    VARCHAR(16)  DEFAULT '',
    merge_target_id VARCHAR(64)  DEFAULT '',
    created_at      TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_decisions_task ON decisions(task_id);

-- ============================================================
-- 6. Debate History（辩论轮次记录）
-- ============================================================
CREATE TABLE IF NOT EXISTS debate_history (
    id                 SERIAL PRIMARY KEY,
    task_id            VARCHAR(128) NOT NULL,
    round_number       INT          DEFAULT 0,
    lead_action        VARCHAR(64)  DEFAULT '',
    target_finding_id  VARCHAR(64)  DEFAULT '',
    actor              VARCHAR(64)  DEFAULT '',
    result_summary     TEXT         DEFAULT '',
    consensus_score    FLOAT        DEFAULT 0.0,
    findings_count     INT          DEFAULT 0,
    created_at         TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_debate_task ON debate_history(task_id);

-- ============================================================
-- 7. RAG 向量存储（pgvector）
-- ============================================================
CREATE TABLE IF NOT EXISTS rag_vectors (
    id              SERIAL PRIMARY KEY,
    chunk_text      TEXT         NOT NULL,
    source_file     TEXT         DEFAULT '',
    section_title   TEXT         DEFAULT '',
    chunk_index     INT          DEFAULT 0,
    embedding       VECTOR(1024) NOT NULL,
    created_at      TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rag_vectors_ivfflat
    ON rag_vectors USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 16);

-- ============================================================
-- 8. 历史审查向量（长期记忆：用于跨任务检索相似审查）
-- ============================================================
CREATE TABLE IF NOT EXISTS review_vectors (
    id              SERIAL PRIMARY KEY,
    task_id         VARCHAR(128) NOT NULL,
    summary_text    TEXT         NOT NULL,
    embedding       VECTOR(1024) NOT NULL,
    created_at      TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_review_vectors_ivfflat
    ON review_vectors USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 8);
