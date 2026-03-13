# TEST-0007: pg-mcp 测试计划

| 字段       | 值                          |
| ---------- | --------------------------- |
| 文档编号   | TEST-0007                   |
| 关联设计   | DES-0002 v0.2               |
| 关联实现   | IMPL-0004 v0.1              |
| 关联 PRD   | PRD-0001 v0.2               |
| 版本       | 0.1 (Draft)                 |
| 创建日期   | 2026-03-12                  |

---

## 1. 测试目标与原则

### 1.1 测试目标

- 验证所有 PRD 功能需求（FR-*）和非功能需求（NFR-*）的正确实现
- 确保 SQL 安全校验器作为最关键安全组件达到 **≥ 98% 代码覆盖率**
- 验证纵深防御体系各层独立有效（AST 校验、只读事务、熔断器、脱敏）
- 整体项目测试覆盖率 **≥ 85%**

### 1.2 测试原则

- **安全测试优先**：SQL Validator 拥有最高密度的测试用例，覆盖所有已知攻击向量
- **分层隔离**：单元测试使用 mock 隔离外部依赖；集成测试使用真实 PostgreSQL；E2E 测试验证完整链路
- **可重复性**：所有测试可在本地和 CI 环境一致运行；集成测试通过 Docker 提供环境
- **快速反馈**：单元测试独立于外部服务，可在秒级完成；耗时测试标记 marker 以支持选择性运行
- **防御性测试**：不仅测试"应该工作"的场景，更重点测试"应该被拒绝"的场景

---

## 2. 测试分层与标记

### 2.1 测试金字塔

```
         ┌──────────────┐
         │   E2E 测试    │  ← FastMCP test client → Pipeline → Mock LLM → Docker PG
         │   (~10 用例)  │
         ├──────────────┤
         │  集成测试      │  ← 真实 asyncpg + Docker PG / Mock LLM
         │  (~40 用例)   │
         ├──────────────┤
         │  单元测试      │  ← 纯逻辑，全部 mock，无 I/O
         │  (~120 用例)  │
         └──────────────┘
```

### 2.2 pytest marker 定义

```python
# conftest.py 或 pyproject.toml [tool.pytest.ini_options]
markers = [
    "unit: 单元测试，无外部依赖，秒级完成",
    "integration: 集成测试，需要 Docker PostgreSQL",
    "e2e: 端到端测试，需要 Docker PostgreSQL + 完整环境",
    "security: 安全相关测试（SQL Validator、只读事务等）",
    "slow: 执行时间 > 5 秒的测试",
]
```

### 2.3 执行命令

```bash
# 仅单元测试（CI 快速反馈）
pytest -m unit

# 单元 + 集成测试
pytest -m "unit or integration"

# 仅安全测试
pytest -m security

# 全量测试
pytest

# 带覆盖率
pytest --cov=pg_mcp --cov-report=html --cov-branch
```

---

## 3. 测试基础设施

### 3.1 目录结构

```
tests/
├── conftest.py                     # 全局 fixtures
├── docker-compose.yml              # 测试用 PostgreSQL
├── fixtures/
│   ├── seed.sql                    # 测试数据库初始化（DDL + 示例数据）
│   ├── seed_permissions.sql        # 权限受限场景的初始化
│   └── large_schema.sql            # 大型 schema 场景（500+ 表）
├── unit/
│   ├── test_config.py
│   ├── test_models.py
│   ├── test_errors.py
│   ├── test_logging.py
│   ├── test_validator.py           # SQL 安全校验（核心）
│   ├── test_circuit_breaker.py
│   ├── test_schema_cache.py
│   ├── test_schema_retriever.py
│   ├── test_prompts.py
│   ├── test_llm_client.py
│   ├── test_verifier.py
│   └── test_pipeline_logic.py      # Pipeline 逻辑（mock 所有依赖）
├── integration/
│   ├── test_executor.py
│   ├── test_schema_collector.py
│   ├── test_pool_manager.py
│   └── test_pipeline_integration.py
└── e2e/
    └── test_e2e.py
```

### 3.2 Docker PostgreSQL 配置

```yaml
# tests/docker-compose.yml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: pgmcp_test
      POSTGRES_PASSWORD: pgmcp_test
      POSTGRES_DB: pgmcp_test
    ports:
      - "15432:5432"
    volumes:
      - ./fixtures/seed.sql:/docker-entrypoint-initdb.d/01-seed.sql
      - ./fixtures/seed_permissions.sql:/docker-entrypoint-initdb.d/02-permissions.sql
    tmpfs:
      - /var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U pgmcp_test"]
      interval: 2s
      timeout: 5s
      retries: 10
```

### 3.3 测试种子数据 (`fixtures/seed.sql`)

```sql
-- 基础业务表
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE,
    department_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE users IS '系统用户表';
COMMENT ON COLUMN users.name IS '用户姓名';
COMMENT ON COLUMN users.email IS '用户邮箱地址';

CREATE TABLE departments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    manager_id INTEGER REFERENCES users(id)
);
COMMENT ON TABLE departments IS '部门表';

ALTER TABLE users ADD CONSTRAINT fk_department
    FOREIGN KEY (department_id) REFERENCES departments(id);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    total NUMERIC(10,2) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_orders_user ON orders(user_id);
CREATE INDEX idx_orders_status ON orders(status);

-- 枚举类型
CREATE TYPE order_status AS ENUM ('pending', 'confirmed', 'shipped', 'delivered', 'cancelled');

-- 视图
CREATE VIEW active_users AS
    SELECT u.*, d.name as department_name
    FROM users u
    LEFT JOIN departments d ON u.department_id = d.id
    WHERE u.created_at > NOW() - INTERVAL '1 year';

-- sales schema 中的表
CREATE TABLE sales.products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price NUMERIC(10,2),
    description TEXT,
    metadata JSONB DEFAULT '{}'::JSONB
);

-- 插入示例数据
INSERT INTO departments (name) VALUES ('Engineering'), ('Marketing'), ('Sales');
INSERT INTO users (name, email, department_id) VALUES
    ('Alice', 'alice@example.com', 1),
    ('Bob', 'bob@example.com', 2),
    ('Charlie', 'charlie@example.com', 3),
    ('Diana', 'diana@example.com', 1);
INSERT INTO orders (user_id, total, status) VALUES
    (1, 100.50, 'confirmed'),
    (1, 200.00, 'shipped'),
    (2, 50.00, 'pending'),
    (3, 300.00, 'delivered');
INSERT INTO sales.products (name, price, description, metadata)
VALUES ('Widget', 9.99, REPEAT('Long description ', 500), '{"category": "tools"}');
```

### 3.4 全局 Fixtures (`conftest.py`)

```python
import pytest
import asyncio
import asyncpg
from unittest.mock import AsyncMock, MagicMock, patch

# --- 事件循环 ---
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

# --- 配置 ---
@pytest.fixture
def server_config():
    """标准 ServerConfig，适用于大多数测试"""
    return ServerConfig(
        databases="testdb",
        statement_timeout="5s",
        lock_timeout="2s",
        default_max_rows=100,
        max_field_size=1024,
        max_payload_size=65536,
        pool_size_per_db=2,
        max_concurrent_queries=5,
        verify_mode="off",
        log_level="DEBUG",
        max_sql_length=10000,
    )

# --- Docker PG ---
@pytest.fixture(scope="session")
async def pg_pool():
    """集成测试用的真实 asyncpg 连接池"""
    pool = await asyncpg.create_pool(
        dsn="postgresql://pgmcp_test:pgmcp_test@localhost:15432/pgmcp_test",
        min_size=1, max_size=3,
    )
    yield pool
    await pool.close()

@pytest.fixture
async def pg_conn(pg_pool):
    """每个测试独立的 PG 连接"""
    conn = await pg_pool.acquire()
    yield conn
    await pg_pool.release(conn)

# --- Mock LLM ---
@pytest.fixture
def mock_llm_client():
    """LLMClient mock，默认返回合法 SQL"""
    client = AsyncMock()
    client.chat.return_value = "SELECT * FROM users"
    return client

# --- Mock Schema ---
@pytest.fixture
def sample_schema():
    """包含 users/departments/orders 的测试用 DatabaseSchema"""
    return DatabaseSchema(
        database_name="testdb",
        schemas=["public"],
        tables=[...],  # 完整的 TableInfo 列表
        enum_types=[...],
        collected_at="2026-03-12T00:00:00Z",
    )
```

---

## 4. 单元测试详细规格

### 4.1 配置模块 (`test_config.py`)

| #  | 测试用例                                           | 输入                                                    | 期望                                       | PRD 需求      |
| -- | -------------------------------------------------- | ------------------------------------------------------- | ------------------------------------------ | ------------- |
| C1 | 默认值加载                                         | 无环境变量（除必填字段）                                | 使用默认超时/行数/连接池等                 | NFR-4.5       |
| C2 | 单数据库配置解析                                   | `PG_MCP_DATABASES=db1`, `PG_MCP_DB1_*` 系列            | 正确构建 1 个 `DatabaseConfig`             | §5.1          |
| C3 | 多数据库配置解析                                   | `PG_MCP_DATABASES=db1,db2`, 各别名环境变量              | 正确构建 2 个 `DatabaseConfig`             | §5.1          |
| C4 | 连接字符串优先                                     | 同时设 `URL` 和 `HOST/PORT`                             | `url` 优先，忽略分离参数                   | DES §3        |
| C5 | `SecretStr` 不泄露                                 | 设置 `password` 和 `api_key`                            | `repr()` / `str()` 不包含明文              | NFR-4.1.2     |
| C6 | 空数据库列表                                       | `PG_MCP_DATABASES=`                                     | 空列表，不报错                             | —             |
| C7 | 非法端口号                                         | `PG_MCP_DB1_PORT=abc`                                   | Pydantic `ValidationError`                 | —             |
| C8 | LLM 配置默认值                                     | 仅设 `api_key`                                          | `base_url=deepseek`, `model=deepseek-chat` | DES §3        |
| C9 | 自定义 blocked_functions                           | `blocked_functions=["custom_fn"]`                       | 合并到默认黑名单                           | FR-2.3-05     |
| C10| 数据库别名大小写                                   | `PG_MCP_DATABASES=MyDB`, `PG_MCP_MYDB_*`               | 正确解析（大小写匹配策略）                 | DES §3        |

---

### 4.2 数据模型 (`test_models.py`)

| #  | 测试用例                                    | 期望                                           |
| -- | ------------------------------------------- | ---------------------------------------------- |
| M1 | `QueryRequest` 默认值                       | `return_mode=RESULT`, `max_rows=100`, `verify_result=False` |
| M2 | `QueryRequest` 枚举校验                     | `return_mode="invalid"` → `ValidationError`    |
| M3 | `QueryResponse` 序列化（成功）              | `exclude_none=True` 后无 `error` 字段          |
| M4 | `QueryResponse` 序列化（错误）              | `exclude_none=True` 后无 `result/sql` 字段     |
| M5 | `ErrorDetail` 完整性                        | 四字段均必填，`retryable` 为 bool               |
| M6 | `ColumnDef` 简单结构                        | `name` + `type` 均为 str                       |
| M7 | `QueryResult` 行列一致性                    | `returned_row_count` == `len(rows)`            |
| M8 | `VerificationResult` 值范围                 | `match` 接受 "yes"/"no"/"partial"/"unknown"    |

---

### 4.3 错误体系 (`test_errors.py`)

| #  | 测试用例                                    | 期望                                           |
| -- | ------------------------------------------- | ---------------------------------------------- |
| E1 | 所有异常继承 `PgMcpError`                   | `isinstance(ValidationError(), PgMcpError)`    |
| E2 | `ValidationError` 携带 code + reason        | 可通过 `.code` 和 `.reason` 访问               |
| E3 | `ExecutionError` 携带 code + message        | 同上                                           |
| E4 | `CircuitOpenError` 携带数据库别名           | `str(err)` 包含别名                            |
| E5 | `EXCEPTION_MAP` 完整映射                    | 每种自定义异常在 map 中有对应条目              |

---

### 4.4 日志脱敏 (`test_logging.py`)

| #  | 测试用例                                         | 输入 event_dict                          | 期望                                         | PRD 需求      |
| -- | ------------------------------------------------ | ---------------------------------------- | -------------------------------------------- | ------------- |
| L1 | 密码字段脱敏                                     | `{"password": "secret123"}`              | `{"password": "***REDACTED***"}`             | NFR-4.4-03    |
| L2 | API Key 脱敏                                     | `{"api_key": "sk-xxx"}`                  | `{"api_key": "***REDACTED***"}`              | NFR-4.4-03    |
| L3 | DSN 脱敏                                         | `{"dsn": "postgres://u:p@h/d"}`         | `{"dsn": "***REDACTED***"}`                  | NFR-4.4-03    |
| L4 | SQL 非 DEBUG 替换为 hash                         | `{"sql": "SELECT 1", "_log_level": "INFO"}` | 无 `sql` 键，有 `sql_hash` 16 字符      | NFR-4.4-03    |
| L5 | SQL DEBUG 级别保留原文                           | `{"sql": "SELECT 1", "_log_level": "DEBUG"}` | `sql` 键保留                            | NFR-4.4-03    |
| L6 | 结果数据行被移除                                 | `{"rows": [[1,2,3]]}`                   | 无 `rows` 键                                 | NFR-4.4-03    |
| L7 | prompt 内容被移除                                | `{"prompt": "system message"}`           | 无 `prompt` 键                               | NFR-4.4-03    |
| L8 | 非敏感字段不受影响                               | `{"event": "query_start", "db": "mydb"}`| 两个字段均保留                               | —             |
| L9 | `configure_logging` DEBUG 使用 ConsoleRenderer   | `level="DEBUG"`                          | structlog 配置不报错                         | —             |
| L10| `configure_logging` INFO 使用 JSONRenderer       | `level="INFO"`                           | structlog 配置不报错                         | —             |

---

### 4.5 SQL 安全校验器 (`test_validator.py`) ★ 核心安全组件

此模块要求 **≥ 98% 覆盖率**，是整个系统的安全基石。

#### 4.5.1 合法查询（应通过）

| #   | 测试用例                      | SQL                                                           | 期望   | PRD 需求   |
| --- | ----------------------------- | ------------------------------------------------------------- | ------ | ---------- |
| V01 | 简单 SELECT                  | `SELECT * FROM users`                                         | 通过   | FR-2.3-03  |
| V02 | 带 WHERE                     | `SELECT name FROM users WHERE id = 1`                         | 通过   | FR-2.3-03  |
| V03 | 带 JOIN                      | `SELECT u.name, d.name FROM users u JOIN departments d ON u.department_id = d.id` | 通过 | FR-2.3-03 |
| V04 | 聚合函数                     | `SELECT department_id, COUNT(*) FROM users GROUP BY 1`        | 通过   | FR-2.3-03  |
| V05 | 子查询                       | `SELECT * FROM (SELECT id FROM users) t`                      | 通过   | FR-2.3-03  |
| V06 | CTE (WITH ... SELECT)        | `WITH t AS (SELECT 1 AS n) SELECT * FROM t`                   | 通过   | FR-2.3-03  |
| V07 | 递归 CTE                     | `WITH RECURSIVE t(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM t WHERE n<10) SELECT * FROM t` | 通过 | FR-2.3-03 |
| V08 | 多 CTE                       | `WITH a AS (SELECT 1), b AS (SELECT 2) SELECT * FROM a, b`   | 通过   | FR-2.3-03  |
| V09 | UNION                        | `SELECT 1 UNION SELECT 2`                                     | 通过   | FR-2.3-03  |
| V10 | INTERSECT                    | `SELECT 1 INTERSECT SELECT 1`                                 | 通过   | FR-2.3-03  |
| V11 | EXCEPT                       | `SELECT 1 EXCEPT SELECT 2`                                    | 通过   | FR-2.3-03  |
| V12 | UNION ALL                    | `SELECT 1 UNION ALL SELECT 2`                                 | 通过   | FR-2.3-03  |
| V13 | EXPLAIN (纯)                 | `EXPLAIN SELECT 1`                                            | 通过   | FR-2.3-03  |
| V14 | 窗口函数                     | `SELECT id, ROW_NUMBER() OVER (ORDER BY id) FROM users`       | 通过   | FR-2.3-03  |
| V15 | LATERAL JOIN                 | `SELECT * FROM users u, LATERAL (SELECT COUNT(*) FROM orders WHERE user_id=u.id) c` | 通过 | FR-2.3-03 |
| V16 | CASE 表达式                  | `SELECT CASE WHEN id > 1 THEN 'yes' ELSE 'no' END FROM users` | 通过  | FR-2.3-03  |
| V17 | 边界值：恰好 10000 字符      | `SELECT 1` + 填充至 10000 chars                               | 通过   | FR-2.3-06  |
| V18 | JSON 操作符                  | `SELECT metadata->>'category' FROM sales.products`             | 通过   | FR-2.3-03  |
| V19 | 安全函数：`NOW()`            | `SELECT NOW()`                                                 | 通过   | FR-2.3-05  |
| V20 | 安全函数：`COUNT/SUM/AVG`    | `SELECT COUNT(*), SUM(total), AVG(total) FROM orders`          | 通过   | FR-2.3-05  |
| V21 | 注释中含危险内容（应忽略注释）| `SELECT 1 -- pg_sleep(100)`                                   | 通过   | REVIEW F3  |

#### 4.5.2 危险查询（应拒绝）— DML/DDL

| #   | 测试用例                      | SQL                                                           | 期望错误码              | PRD 需求   |
| --- | ----------------------------- | ------------------------------------------------------------- | ----------------------- | ---------- |
| V30 | INSERT                       | `INSERT INTO users(name) VALUES ('x')`                        | `DISALLOWED_STATEMENT`  | FR-2.3-04  |
| V31 | UPDATE                       | `UPDATE users SET name='x'`                                   | `DISALLOWED_STATEMENT`  | FR-2.3-04  |
| V32 | DELETE                       | `DELETE FROM users`                                           | `DISALLOWED_STATEMENT`  | FR-2.3-04  |
| V33 | TRUNCATE                     | `TRUNCATE users`                                              | `DISALLOWED_STATEMENT`  | FR-2.3-04  |
| V34 | CREATE TABLE                 | `CREATE TABLE t (a int)`                                      | `DISALLOWED_STATEMENT`  | FR-2.3-04  |
| V35 | CREATE TEMP TABLE AS         | `CREATE TEMP TABLE t AS SELECT 1`                             | `DISALLOWED_STATEMENT`  | FR-2.3-04  |
| V36 | DROP TABLE                   | `DROP TABLE users`                                            | `DISALLOWED_STATEMENT`  | FR-2.3-04  |
| V37 | ALTER TABLE                  | `ALTER TABLE users ADD COLUMN x int`                          | `DISALLOWED_STATEMENT`  | FR-2.3-04  |
| V38 | GRANT                        | `GRANT SELECT ON users TO PUBLIC`                             | `DISALLOWED_STATEMENT`  | FR-2.3-04  |
| V39 | SET                          | `SET statement_timeout = 0`                                   | `DISALLOWED_STATEMENT`  | FR-2.3-04  |
| V40 | COPY TO                      | `COPY users TO '/tmp/x'`                                     | `DISALLOWED_STATEMENT`  | FR-2.3-04  |
| V41 | COPY FROM                    | `COPY users FROM '/tmp/x'`                                   | `DISALLOWED_STATEMENT`  | FR-2.3-04  |
| V42 | SELECT INTO                  | `SELECT * INTO t FROM users`                                  | `SELECT_INTO`           | FR-2.3-04  |

#### 4.5.3 危险查询（应拒绝）— 多语句 / 结构

| #   | 测试用例                      | SQL                                                           | 期望错误码              | PRD 需求   |
| --- | ----------------------------- | ------------------------------------------------------------- | ----------------------- | ---------- |
| V50 | 多语句分号                   | `SELECT 1; DROP TABLE x`                                      | `MULTIPLE_STATEMENTS`   | FR-2.3-02  |
| V51 | 多 SELECT 分号               | `SELECT 1; SELECT 2`                                          | `MULTIPLE_STATEMENTS`   | FR-2.3-02  |
| V52 | CTE 体为 INSERT              | `WITH t AS (INSERT INTO x VALUES(1) RETURNING *) SELECT * FROM t` | `DISALLOWED_STATEMENT` | FR-2.3-04 |
| V53 | CTE 体为 DELETE              | `WITH t AS (DELETE FROM users RETURNING *) SELECT * FROM t`   | `DISALLOWED_STATEMENT`  | FR-2.3-04  |
| V54 | CTE + 外层 INSERT            | `WITH t AS (SELECT 1) INSERT INTO x SELECT * FROM t`          | `DISALLOWED_STATEMENT`  | FR-2.3-04  |
| V55 | 超长 SQL (10001 字符)        | 10001 字符的 SELECT                                           | `QUERY_TOO_LONG`        | FR-2.3-06  |
| V56 | 空字符串                     | `""`                                                          | `PARSE_ERROR`           | —          |
| V57 | 仅空白字符                   | `"   \n\t  "`                                                 | `PARSE_ERROR`           | —          |
| V58 | 非法 SQL 语法                | `SELEC FROM users`                                            | `PARSE_ERROR`           | FR-2.3-01  |
| V59 | EXPLAIN ANALYZE              | `EXPLAIN ANALYZE SELECT 1`                                    | `EXPLAIN_ANALYZE`       | FR-2.3-03  |
| V60 | EXPLAIN (ANALYZE)            | `EXPLAIN (ANALYZE) SELECT 1`                                  | `EXPLAIN_ANALYZE`       | REVIEW F4  |
| V61 | EXPLAIN (ANALYZE, BUFFERS)   | `EXPLAIN (ANALYZE, BUFFERS) SELECT 1`                         | `EXPLAIN_ANALYZE`       | REVIEW F4  |
| V62 | EXPLAIN DELETE               | `EXPLAIN DELETE FROM users`                                   | `DISALLOWED_STATEMENT`  | REVIEW F4  |
| V63 | EXPLAIN INSERT               | `EXPLAIN INSERT INTO t VALUES(1)`                             | `DISALLOWED_STATEMENT`  | REVIEW F4  |

#### 4.5.4 危险查询（应拒绝）— 危险函数

| #   | 测试用例                      | SQL                                                           | 期望错误码          | PRD 需求   |
| --- | ----------------------------- | ------------------------------------------------------------- | ------------------- | ---------- |
| V70 | pg_sleep                     | `SELECT pg_sleep(100)`                                        | `BLOCKED_FUNCTION`  | FR-2.3-05  |
| V71 | pg_sleep 大小写              | `SELECT PG_SLEEP(100)`                                        | `BLOCKED_FUNCTION`  | REVIEW F5  |
| V72 | pg_sleep schema限定          | `SELECT pg_catalog.pg_sleep(100)`                             | `BLOCKED_FUNCTION`  | REVIEW F5  |
| V73 | dblink                       | `SELECT * FROM dblink('host=x')`                              | `BLOCKED_FUNCTION`  | FR-2.3-05  |
| V74 | dblink_exec                  | `SELECT dblink_exec('DROP TABLE x')`                          | `BLOCKED_FUNCTION`  | FR-2.3-05  |
| V75 | lo_export                    | `SELECT lo_export(12345, '/tmp/x')`                           | `BLOCKED_FUNCTION`  | FR-2.3-05  |
| V76 | lo_import                    | `SELECT lo_import('/tmp/x')`                                  | `BLOCKED_FUNCTION`  | FR-2.3-05  |
| V77 | pg_read_file                 | `SELECT pg_read_file('/etc/passwd')`                          | `BLOCKED_FUNCTION`  | FR-2.3-05  |
| V78 | pg_read_binary_file          | `SELECT pg_read_binary_file('/etc/passwd')`                   | `BLOCKED_FUNCTION`  | FR-2.3-05  |
| V79 | pg_write_file                | `SELECT pg_write_file('/tmp/x', 'data')`                      | `BLOCKED_FUNCTION`  | FR-2.3-05  |
| V80 | pg_stat_file                 | `SELECT pg_stat_file('/etc/passwd')`                          | `BLOCKED_FUNCTION`  | FR-2.3-05  |
| V81 | set_config                   | `SELECT set_config('statement_timeout', '0', false)`          | `BLOCKED_FUNCTION`  | FR-2.3-05  |
| V82 | pg_terminate_backend         | `SELECT pg_terminate_backend(1234)`                           | `BLOCKED_FUNCTION`  | FR-2.3-05  |
| V83 | pg_cancel_backend            | `SELECT pg_cancel_backend(1234)`                              | `BLOCKED_FUNCTION`  | FR-2.3-05  |
| V84 | pg_advisory_lock             | `SELECT pg_advisory_lock(1)`                                  | `BLOCKED_FUNCTION`  | FR-2.3-05  |
| V85 | pg_try_advisory_lock         | `SELECT pg_try_advisory_lock(1)`                              | `BLOCKED_FUNCTION`  | FR-2.3-05  |
| V86 | pg_advisory_xact_lock        | `SELECT pg_advisory_xact_lock(1)`                             | `BLOCKED_FUNCTION`  | FR-2.3-05  |
| V87 | pg_notify                    | `SELECT pg_notify('channel', 'msg')`                          | `BLOCKED_FUNCTION`  | FR-2.3-05  |
| V88 | pg_create_logical_replication_slot | `SELECT pg_create_logical_replication_slot('s','p')`    | `BLOCKED_FUNCTION`  | FR-2.3-05  |
| V89 | pg_drop_replication_slot     | `SELECT pg_drop_replication_slot('s')`                        | `BLOCKED_FUNCTION`  | FR-2.3-05  |
| V90 | pg_start_backup              | `SELECT pg_start_backup('label')`                             | `BLOCKED_FUNCTION`  | FR-2.3-05  |
| V91 | pg_reload_conf               | `SELECT pg_reload_conf()`                                     | `BLOCKED_FUNCTION`  | FR-2.3-05  |
| V92 | pg_switch_wal                | `SELECT pg_switch_wal()`                                      | `BLOCKED_FUNCTION`  | FR-2.3-05  |

#### 4.5.5 危险查询（应拒绝）— 嵌套 / 隐藏

| #    | 测试用例                         | SQL                                                           | 期望错误码          | 来源       |
| ---- | -------------------------------- | ------------------------------------------------------------- | ------------------- | ---------- |
| V100 | 子查询中的 pg_sleep              | `SELECT * FROM (SELECT pg_sleep(1)) t`                        | `BLOCKED_FUNCTION`  | IMPL 补充  |
| V101 | CTE 中的 pg_sleep                | `WITH t AS (SELECT pg_sleep(1)) SELECT * FROM t`              | `BLOCKED_FUNCTION`  | IMPL 补充  |
| V102 | CASE 中的 pg_sleep               | `SELECT CASE WHEN 1=1 THEN pg_sleep(1) END`                   | `BLOCKED_FUNCTION`  | 补充       |
| V103 | WHERE 中的危险函数               | `SELECT 1 WHERE pg_sleep(1) IS NOT NULL`                       | `BLOCKED_FUNCTION`  | 补充       |
| V104 | 嵌套函数调用                     | `SELECT lo_export(lo_import('/tmp/a'), '/tmp/b')`              | `BLOCKED_FUNCTION`  | 补充       |
| V105 | schema限定 + 嵌套                | `SELECT * FROM (SELECT pg_catalog.pg_read_file('/etc/passwd')) t` | `BLOCKED_FUNCTION` | REVIEW F5 |
| V106 | 自定义 blocked_functions         | 配置 `["custom_fn"]`，SQL `SELECT custom_fn()`                 | `BLOCKED_FUNCTION`  | FR-2.3-05  |

#### 4.5.6 CTE / WITH 特殊处理（来自 REVIEW F3）

| #    | 测试用例                              | 验证点                                                    |
| ---- | ------------------------------------- | --------------------------------------------------------- |
| V110 | 打印 `WITH...SELECT` 的 SQLGlot AST  | 记录根节点类型（`exp.Select` 还是 `exp.With`），确保白名单策略正确 |
| V111 | `WITH RECURSIVE ... SELECT` 根节点    | 同上，验证递归 CTE 的 AST 结构                            |
| V112 | `WITH ... UNION` 根节点               | 验证 CTE + UNION 的 AST 结构                             |
| V113 | 多层嵌套 CTE                          | `WITH a AS (WITH b AS (SELECT 1) SELECT * FROM b) SELECT * FROM a` |

---

### 4.6 熔断器 (`test_circuit_breaker.py`)

| #  | 测试用例                                           | 初始状态   | 动作                              | 期望最终状态 / 行为                    | PRD 需求    |
| -- | -------------------------------------------------- | ---------- | --------------------------------- | -------------------------------------- | ----------- |
| B1 | 正常请求不影响状态                                 | CLOSED     | 1 次成功                          | CLOSED, `failure_count=0`              | NFR-4.3-04  |
| B2 | 非熔断错误不计数                                   | CLOSED     | 抛出 `PostgresSyntaxError`        | CLOSED, `failure_count=0`              | DES §5.3    |
| B3 | 熔断错误累加                                       | CLOSED     | 4 次 `TimeoutError`              | CLOSED, `failure_count=4`              | NFR-4.3-04  |
| B4 | 达到阈值触发熔断                                   | CLOSED     | 5 次连续 `TimeoutError`          | OPEN                                   | NFR-4.3-04  |
| B5 | 熔断状态拒绝请求                                   | OPEN       | 立即请求                          | 抛出 `CircuitOpenError`                | NFR-4.3-04  |
| B6 | 等待恢复超时后转半开                               | OPEN       | 等待 > `recovery_timeout`        | HALF_OPEN                              | NFR-4.3-04  |
| B7 | 半开状态试探成功恢复                               | HALF_OPEN  | 1 次成功                          | CLOSED, `failure_count=0`              | NFR-4.3-04  |
| B8 | 半开状态试探失败重新熔断                           | HALF_OPEN  | 1 次 `TimeoutError`              | OPEN（重置计时器）                     | NFR-4.3-04  |
| B9 | 半开状态仅允许单请求试探                           | HALF_OPEN  | 并发 2 个请求                     | 仅 1 个通过，另 1 个 `CircuitOpenError`| DES §5.3    |
| B10| 成功后重置失败计数                                 | CLOSED     | 3 次失败 → 1 次成功 → 检查       | `failure_count=0`                      | DES §5.3    |
| B11| `ConnectionError` 触发熔断                         | CLOSED     | 5 次 `ConnectionError`           | OPEN                                   | DES §5.3    |
| B12| `OSError` 触发熔断                                 | CLOSED     | 5 次 `OSError`                   | OPEN                                   | DES §5.3    |
| B13| `InterfaceError` 触发熔断                          | CLOSED     | 5 次 `InterfaceError`            | OPEN                                   | DES §5.3    |
| B14| `InternalServerError` 触发熔断                     | CLOSED     | 5 次 `InternalServerError`       | OPEN                                   | DES §5.3    |
| B15| `QueryCanceledError` 不触发熔断                    | CLOSED     | 10 次 `QueryCanceledError`       | CLOSED                                 | DES §5.3    |

---

### 4.7 Schema 缓存 (`test_schema_cache.py`)

| #  | 测试用例                            | 方法                                     | 期望                                       |
| -- | ----------------------------------- | ---------------------------------------- | ------------------------------------------ |
| S1 | 首次加载触发 collector              | `get_or_load("db1", ...)`               | 调用 collector 1 次，缓存命中              |
| S2 | 缓存命中不再调用 collector          | 第 2 次 `get_or_load("db1", ...)`       | collector 调用次数仍为 1                   |
| S3 | TTL 过期自动刷新                    | 设 TTL=0.1s, sleep(0.2s), get_or_load   | collector 调用第 2 次                      |
| S4 | 并发加载只触发一次 collector        | asyncio.gather 5 个 `get_or_load`       | collector 仅调用 1 次                      |
| S5 | 超过 max_tables 截断并警告          | collector 返回 600 表，max=500           | 缓存中仅 500 表，log warning               |
| S6 | `refresh` 清除并重新加载            | 已缓存 → refresh → get_or_load          | collector 被调用 2 次                      |
| S7 | `refresh(None)` 刷新所有            | 多库已缓存 → refresh(None)              | 所有库重新加载                             |
| S8 | `warm_up` 采集摘要                  | warm_up 后检查 `_summaries`             | 每库有 summary entry                       |
| S9 | `warm_up` 单库失败不阻塞            | 某库连接失败                             | 其他库 summary 正常，有 warning log        |
| S10| `list_databases` 返回摘要列表       | warm_up 后调用                           | 返回 list[dict]，含数据库名                |

---

### 4.8 Schema 检索增强 (`test_schema_retriever.py`)

| #  | 测试用例                              | 输入                                      | 期望                                   |
| -- | ------------------------------------- | ----------------------------------------- | -------------------------------------- |
| R1 | 精确表名匹配权重最高                  | question="查询 users", schema 含 users 表 | users 排第一                           |
| R2 | 列名匹配                             | question="查询 email", schema 含 users.email | users 被选中                         |
| R3 | 注释匹配                             | question="用户姓名", users.name 注释含"姓名"| users 被选中                         |
| R4 | 多表相关均被选中                      | question="用户订单"                       | users + orders 均被选中                |
| R5 | 字符预算裁剪                          | `max_context_chars=100`, 大 schema        | 仅选中能装入预算的表                   |
| R6 | 零匹配 fallback                      | question="完全无关内容"                   | 返回前 10 表                           |
| R7 | 空 schema                            | question="任意", schema.tables=[]         | 返回空列表                             |
| R8 | `render_schema_context` 格式          | 多表含列+外键+注释                        | 格式如 `schema.table (col type, ...)`  |
| R9 | `render_schema_context` 注释截断      | 表注释 > 500 字符                         | 注释被截断到 500                       |
| R10| `render_schema_context` 外键渲染      | 表有外键                                  | 包含 `FK: col → target.col`           |
| R11| `_tokenize` 中文分词                 | question="查询所有用户的订单"             | 包含有意义的 token                     |
| R12| 单字母 token 过滤                    | question="a b users"                      | "a"/"b" 不参与评分                     |

---

### 4.9 Prompt 模板 (`test_prompts.py`)

| #  | 测试用例                           | 期望                                              |
| -- | ---------------------------------- | ------------------------------------------------- |
| P1 | SQL 生成 system prompt 含占位符    | 包含 `{schema_context}` 占位符                    |
| P2 | SQL 生成 user prompt 含占位符      | 包含 `{question}` 占位符                          |
| P3 | `build_sql_generation_prompt` 渲染 | 正确替换 schema_context 和 question               |
| P4 | 验证 prompt 含 JSON 格式要求       | 包含 `match` / `explanation` / `suggested_sql`    |
| P5 | DB 选择 prompt 含数据库摘要占位符  | 包含 `{db_summaries}` 占位符                      |
| P6 | system prompt 包含只读指令         | 包含"SELECT"/"read-only"等关键词                  |
| P7 | system prompt 包含禁止函数提示     | 包含"pg_sleep"/"dblink"等                          |
| P8 | prompt 渲染后总长度控制            | 大 schema → 总长度不超过预设上限                  |

---

### 4.10 LLM 客户端 (`test_llm_client.py`)

| #  | 测试用例                           | Mock 行为                                    | 期望                                   |
| -- | ---------------------------------- | -------------------------------------------- | -------------------------------------- |
| LC1| 正常响应                          | 返回 `"SELECT * FROM users"`                | 返回该字符串（strip 后）               |
| LC2| 响应包含 markdown 代码块          | 返回 `` ```sql\nSELECT 1\n``` ``           | 提取出 `SELECT 1`                      |
| LC3| 响应包含多个代码块                | 返回多段文字+多代码块                        | 提取第一个 SQL 代码块                  |
| LC4| 响应包含解释+SQL                  | `"Here is the query:\nSELECT 1"`           | 正确提取 SQL 部分                      |
| LC5| API 网络错误                      | 抛出 `APIConnectionError`                   | 转换为 `LLMError`                      |
| LC6| API 认证失败                      | 抛出 `AuthenticationError`                  | 转换为 `LLMError`                      |
| LC7| API 限流                         | 抛出 `RateLimitError`                       | 转换为 `LLMError`, retryable           |
| LC8| 响应为空内容                      | `choices[0].message.content = ""`           | 抛出 `LLMParseError`                   |
| LC9| 响应无 SQL 内容                   | 返回 `"I cannot help with that"`            | 抛出 `LLMParseError`                   |
| LC10| 使用自定义 max_tokens             | `chat(max_tokens=2048)`                     | API 调用参数中 `max_tokens=2048`       |
| LC11| 使用配置的 temperature            | config `temperature=0.0`                    | API 调用参数中 `temperature=0.0`       |

---

### 4.11 语义验证器 (`test_verifier.py`)

| #  | 测试用例                                    | 配置                          | 请求               | 期望                                       | PRD 需求   |
| -- | ------------------------------------------- | ----------------------------- | ------------------ | ------------------------------------------ | ---------- |
| VF1| `verify_mode=off` + `verify_result=false`  | `off`                         | `false`            | `should_verify` → False                    | FR-2.5-01  |
| VF2| `verify_mode=off` + `verify_result=true`   | `off`                         | `true`             | `should_verify` → False（配置优先）        | FR-2.5-01  |
| VF3| `verify_mode=metadata` + `verify_result=false` | `metadata`                | `false`            | `should_verify` → False                    | DES §5.8   |
| VF4| `verify_mode=metadata` + `verify_result=true`  | `metadata`                | `true`             | `should_verify` → True, metadata 模式     | DES §5.8   |
| VF5| `verify_mode=sample` + `verify_result=false`   | `sample`                  | `false`            | `should_verify` → False                    | DES §5.8   |
| VF6| `verify_mode=sample` + `verify_result=true`    | `sample`                  | `true`             | `should_verify` → True, sample 模式       | DES §5.8   |
| VF7| metadata context 格式                       | `metadata`                    | —                  | 包含 Columns, Row count, Truncated         | FR-2.5-02  |
| VF8| sample context 行数限制                     | `sample`, `verify_sample_rows=3`| 10 行结果       | context 仅包含 3 行                        | FR-2.5-02  |
| VF9| sample context 字段截断                     | `sample`                      | 字段值 > 100 chars| 每个值截断到 100 chars                     | DES §5.8   |
| VF10| LLM 返回合法 JSON                          | —                             | —                  | 正确解析 match/explanation                 | FR-2.5-04  |
| VF11| LLM 返回非法 JSON                          | —                             | —                  | 容错：`match="unknown"`                   | 补充       |
| VF12| LLM 返回含 suggested_sql                    | —                             | —                  | `suggested_sql` 字段正确传递               | FR-2.5-05  |
| VF13| 空结果集的验证                              | `metadata`                    | 0 行结果           | context 正确显示 `Row count: 0`            | 补充       |

---

### 4.12 Pipeline 逻辑 (`test_pipeline_logic.py`)

| #   | 测试用例                                    | Mock 设定                                       | 期望                                          | PRD 需求      |
| --- | ------------------------------------------- | ----------------------------------------------- | --------------------------------------------- | ------------- |
| PL1 | 正常 result 模式完整流程                    | LLM→合法SQL, PG→结果行                          | QueryResponse 含 sql + result                 | §6 全流程     |
| PL2 | sql 模式不执行                              | LLM→合法SQL                                     | QueryResponse 含 sql, 无 result               | FR-2.6-01     |
| PL3 | 显式指定 database                           | request.database="testdb"                       | 不调用 match_database 逻辑                    | FR-2.2.1-01   |
| PL4 | 本地数据库推断成功                          | schema 包含 users 表                             | 正确选择含 users 的数据库                     | FR-2.2.2-04   |
| PL5 | 本地推断失败→LLM 辅助                       | 本地无匹配, LLM 返回 "db1"                      | 选择 db1                                      | FR-2.2.2-04   |
| PL6 | LLM 返回未知数据库                          | LLM 返回 "unknown_db"                           | 抛出 `AmbiguousDBError`                       | FR-2.2.2-04   |
| PL7 | SQL 校验失败                                | LLM→`INSERT INTO ...`                           | 返回 error, code=`VALIDATION_FAILED`          | FR-2.3-07     |
| PL8 | SQL 校验失败时不返回 SQL                    | 同上                                             | response.sql 为 None                          | FR-2.3-07     |
| PL9 | 执行超时                                    | executor 抛出 `ExecutionError(TIMEOUT)`          | 返回 error, code=`EXECUTION_TIMEOUT`, retryable=True | FR-2.4-05 |
| PL10| LLM 服务不可用                              | LLM 抛出 `LLMError`                             | 返回 error, code=`LLM_ERROR`, retryable=True | NFR-4.3-02    |
| PL11| 熔断触发                                    | pool 抛出 `CircuitOpenError`                     | 返回 error, code=`DB_CIRCUIT_OPEN`, retryable=True | NFR-4.3-04 |
| PL12| 并发限制                                    | semaphore 已满                                   | 返回 error, code=`RATE_LIMITED`               | FR-2.4-03     |
| PL13| 异常映射完整性                              | 逐一触发 EXCEPTION_MAP 中的异常                  | 每种异常正确映射到 ErrorDetail                | DES §7        |
| PL14| `_current_stage` 正确追踪                   | 各阶段中断                                       | error.stage 反映实际中断阶段                  | FR-2.6-04     |
| PL15| 验证重试成功路径                            | 首次 verify→no + suggested_sql, 第 2 次→yes     | 第 2 次 SQL 被执行并返回结果                  | FR-2.5-05     |
| PL16| 验证重试—建议 SQL 校验失败                   | suggested_sql 不通过 validator                   | 返回原结果（不使用非法 SQL）                  | REVIEW F9     |
| PL17| 验证重试—达到上限                            | 3 次均 verify→no                                 | 返回最后一次结果                              | FR-2.5-05     |
| PL18| 验证重试—无 suggested_sql                    | verify→no, 无 suggested_sql                      | 直接返回当前结果（不重试）                    | REVIEW F9     |
| PL19| 单库场景自动选择唯一库                      | 仅配置 1 个数据库                                | 直接使用该库，不调用推断                      | 补充          |

---

## 5. 集成测试详细规格

### 5.1 SQL 执行器 (`integration/test_executor.py`)

需要 Docker PostgreSQL。

| #   | 测试用例                              | 操作                                              | 期望                                           | PRD 需求   |
| --- | ------------------------------------- | ------------------------------------------------- | ---------------------------------------------- | ---------- |
| IE1 | 正常只读查询                          | `SELECT * FROM users`                             | 返回 QueryResult, 行数正确                     | FR-2.4-01  |
| IE2 | 只读事务拒绝写操作                    | `INSERT INTO users(name) VALUES('x')`             | PG 侧抛出只读事务错误                          | FR-2.4-02  |
| IE3 | `statement_timeout` 生效              | `SELECT pg_sleep(10)` (timeout 设为 1s)           | `EXECUTION_TIMEOUT` 错误                       | FR-2.4-02  |
| IE4 | `search_path` 限制                    | `SELECT * FROM products` (仅 public 在 search_path) | PG 报 relation 不存在                       | DES §5.7   |
| IE5 | schema 限定名正常                     | `SELECT * FROM sales.products`                    | 正常返回结果                                   | DES §5.7   |
| IE6 | 空结果集列元数据                      | `SELECT id, name FROM users WHERE 1=0`            | columns 正确，rows=[], returned_row_count=0    | DES §5.7   |
| IE7 | 行数限制 (max_rows)                   | `SELECT * FROM generate_series(1,200)`, max_rows=5| 返回 5 行，truncated=True                      | FR-2.4-04  |
| IE8 | 字符串字段截断                        | 查询含长文本字段                                  | 超 max_field_size 的字段被截断 + `[truncated]` | FR-2.4-04  |
| IE9 | JSONB 字段截断                        | 查询含大 JSONB 字段                               | 超大 JSON 被截断                               | DES §5.7   |
| IE10| bytes 字段截断                        | 查询含 BYTEA 字段                                 | `<binary N bytes, truncated>`                  | DES §5.7   |
| IE11| payload 大小裁剪                      | 查询大量行使 payload > max_payload_size           | 行被裁剪，truncated=True                       | FR-2.4-04  |
| IE12| 错误脱敏：表名移除                    | 查询不存在的表                                    | 错误消息中表名被 `[redacted]`                  | FR-2.4-05  |
| IE13| 错误脱敏：DETAIL 移除                 | 触发含 DETAIL 的 PG 错误                          | 错误消息中 DETAIL 被 `[redacted]`              | DES §5.7   |
| IE14| 错误脱敏：HINT 移除                   | 触发含 HINT 的 PG 错误                            | HINT 被移除                                    | DES §5.7   |
| IE15| 连接获取超时                          | 耗尽连接池后再请求                                | 适当的超时错误                                 | FR-2.4-03  |
| IE16| `conn.prepare()` 列类型名称          | `SELECT 1::int, 'a'::text, NOW()::timestamp`     | 列类型为 PG 类型名（int4, text, timestamp）    | DES Q1     |
| IE17| PG 侧只读事务拒绝 CREATE TEMP TABLE  | 在只读事务中执行 `CREATE TEMP TABLE t AS SELECT 1`| PG 报只读事务不允许                             | REVIEW F6  |

---

### 5.2 Schema 采集器 (`integration/test_schema_collector.py`)

| #   | 测试用例                              | 操作                                              | 期望                                           |
| --- | ------------------------------------- | ------------------------------------------------- | ---------------------------------------------- |
| IS1 | 完整采集 public schema                | `collect_full(conn)`                              | 包含 users, departments, orders 表             |
| IS2 | 列信息完整                            | 检查 users 表的列                                 | name, type, nullable, is_primary_key 均正确    |
| IS3 | 外键关系                              | 检查 users 表的外键                               | department_id → departments.id                 |
| IS4 | 索引信息                              | 检查 orders 表的索引                              | idx_orders_user, idx_orders_status             |
| IS5 | 枚举类型                              | 检查 enum 类型                                    | order_status 含 5 个值                         |
| IS6 | 视图定义                              | 检查 active_users 视图                            | 有 view_definition 字段                        |
| IS7 | 表/列注释                             | 检查 users 表和 name 列注释                       | 注释内容正确                                   |
| IS8 | 多 schema 采集                        | 检查 sales.products                               | 包含在结果中                                   |
| IS9 | 行估计值                              | 检查 users 表的 row_estimate                      | `reltuples` 非 None（ANALYZE 后）              |
| IS10| summary 采集                          | `collect_summary(conn)`                           | 含 public + sales schema 的表计数              |
| IS11| 空数据库                              | 对空数据库采集                                    | 返回空 tables 列表，不报错                     |
| IS12| 权限不足降级                          | 用无 pg_catalog 权限的用户                        | 缺失字段为 None，有 warning log                |

---

### 5.3 连接池管理 (`integration/test_pool_manager.py`)

| #   | 测试用例                              | 操作                                              | 期望                                           |
| --- | ------------------------------------- | ------------------------------------------------- | ---------------------------------------------- |
| IP1 | `initialize()` 创建连接池            | 启动 PoolManager                                  | pools 字典含对应数据库                         |
| IP2 | `initialize()` 单库失败不阻塞         | 配置一个可达 + 一个不可达数据库                   | 可达库正常，不可达库记录错误                   |
| IP3 | `close()` 关闭所有池                  | 初始化后关闭                                      | 所有 pool 已关闭                               |
| IP4 | semaphore 并发限制                    | 设 max=2, 同时发 3 个请求                         | 第 3 个请求等待                                |
| IP5 | acquire + release 正常流程             | acquire → 执行查询 → release                     | 连接正常释放回池                               |

---

### 5.4 Pipeline 集成 (`integration/test_pipeline_integration.py`)

| #   | 测试用例                              | 环境                                              | 期望                                           |
| --- | ------------------------------------- | ------------------------------------------------- | ---------------------------------------------- |
| IT1 | 完整 result 流程 (mock LLM)          | Docker PG + mock LLM 返回合法 SQL                 | 返回正确的查询结果                             |
| IT2 | sql 模式 (mock LLM)                  | Docker PG + mock LLM                              | 仅返回 SQL，无 result                          |
| IT3 | LLM 返回危险 SQL                     | mock LLM 返回 `DELETE FROM users`                | VALIDATION_FAILED 错误，无 SQL 泄露             |
| IT4 | Schema 懒加载触发                    | 首次查询触发 schema 采集                          | schema 采集发生且缓存                          |
| IT5 | Schema 缓存命中                      | 第 2 次查询                                       | 不再采集 schema                                |

---

## 6. 端到端测试 (`e2e/test_e2e.py`)

使用 FastMCP test client 模拟完整 MCP 交互。

| #  | 场景                                         | 输入                                          | 期望输出                                       | PRD 需求     |
| -- | -------------------------------------------- | --------------------------------------------- | ---------------------------------------------- | ------------ |
| E1 | 简单查询                                    | `question="查询所有用户"`                     | 返回 4 行用户数据, columns 含 id/name/email    | §6 全流程    |
| E2 | 聚合查询                                    | `question="每个部门有多少人"`                 | GROUP BY 结果正确                              | §6           |
| E3 | JOIN 查询                                   | `question="用户及其订单金额"`                 | 多表关联结果                                   | §6           |
| E4 | sql 模式                                    | `question="显示所有用户的查询SQL"`, `return_mode="sql"` | sql 字段非空, result 为 None        | FR-2.6-01    |
| E5 | 大结果集截断                                | `question=...`, `max_rows=2`                  | `truncated=True`, `returned_row_count=2`       | FR-2.4-04    |
| E6 | 空结果集                                    | `question="查询2099年创建的用户"`             | `rows=[]`, `columns` 有值                      | DES §5.7     |
| E7 | 不存在的数据库                              | `database="nonexistent"`                      | `error.code="DB_UNAVAILABLE"`                  | §7           |
| E8 | LLM 生成危险 SQL（模拟）                    | mock LLM 返回 `DROP TABLE users`              | `error.code="VALIDATION_FAILED"`, 无 sql 字段  | FR-2.3-07    |
| E9 | tool 注册正确                               | 列出 server tools                             | 包含名为 "query" 的 tool                       | §3           |
| E10| tool 参数 schema 正确                       | 检查 query tool 的参数定义                    | 含 question(必填), database, return_mode 等    | §3.1         |

---

## 7. 安全专项测试

本节汇总所有安全相关测试的专项视角，确保纵深防御的每一层独立有效。

### 7.1 防御层验证矩阵

| 防御层             | 测试范围                    | 关键用例编号                          | 验证方式            |
| ------------------ | --------------------------- | ------------------------------------- | ------------------- |
| AST 白名单         | DML/DDL 全部被拒             | V30-V42, V50-V63                      | 单元测试            |
| 函数黑名单         | 30+ 危险函数被拒             | V70-V92, V100-V106                    | 单元测试            |
| 只读事务           | PG 侧拒绝写入               | IE2, IE17                             | 集成测试（真实 PG） |
| search_path 隔离   | 非限定名不解析到意外 schema  | IE4, IE5                              | 集成测试（真实 PG） |
| 超时保护           | 慢查询被超时取消             | IE3                                   | 集成测试（真实 PG） |
| 错误脱敏           | 无内部信息泄露               | IE12-IE14, L1-L8                      | 集成 + 单元测试     |
| 凭据保护           | SecretStr 不泄露             | C5                                    | 单元测试            |
| 校验失败不返回 SQL | 安全校验失败时 sql=None      | PL7, PL8, E8                          | 单元 + E2E          |
| 熔断器             | 持续失败触发保护             | B1-B15                                | 单元测试            |
| 并发限制           | 超限时拒绝                   | PL12                                  | 单元测试            |

### 7.2 攻击向量覆盖

| 攻击向量                      | 对应测试                                                  |
| ----------------------------- | --------------------------------------------------------- |
| SQL 注入（多语句）            | V50, V51                                                  |
| SQL 注入（DML 嵌入 CTE）     | V52, V53, V54                                             |
| 文件读取                      | V77, V78, V105                                            |
| 文件写入                      | V79                                                       |
| DoS（pg_sleep）               | V70-V72, V100-V103                                        |
| DoS（超长 SQL）               | V55                                                       |
| DoS（advisory lock）          | V84-V86                                                   |
| 数据库外带（dblink）          | V73, V74                                                  |
| 大对象操控                    | V75, V76                                                  |
| 系统管理操作                  | V82, V83, V91, V92                                        |
| 函数黑名单绕过（大小写）      | V71                                                       |
| 函数黑名单绕过（schema限定）  | V72, V105                                                 |
| 信息泄露（错误消息）          | IE12-IE14                                                 |
| 信息泄露（日志）              | L1-L8                                                     |

---

## 8. 性能基线测试

非阻塞性测试，记录基线指标用于回归监控。标记 `@pytest.mark.slow`。

| #  | 测试用例                    | 操作                                          | 采集指标                               | 基线阈值        |
| -- | --------------------------- | --------------------------------------------- | -------------------------------------- | --------------- |
| PF1| Validator 吞吐量            | 对 100 个 SELECT 语句循环校验                 | 平均每次校验耗时                       | < 10ms/条       |
| PF2| SchemaRetriever 性能        | 对 500 表 schema 执行关键词检索               | 检索耗时                               | < 50ms          |
| PF3| Executor 行处理性能         | 查询返回 10000 行，max_rows=100               | 截断 + 序列化总耗时                    | < 100ms         |
| PF4| Payload 裁剪性能            | 构造 10MB payload，裁剪到 5MB                 | 裁剪耗时                               | < 200ms         |
| PF5| 并发查询吞吐                | 20 并发 mock 查询                             | 全部完成总耗时                         | < 5s            |

---

## 9. 测试数据管理

### 9.1 数据准备策略

| 层级       | 数据来源                                  | 生命周期                     |
| ---------- | ----------------------------------------- | ---------------------------- |
| 单元测试   | 代码内构造（Pydantic 模型实例 / 字面量）  | 每个测试函数独立             |
| 集成测试   | `fixtures/seed.sql` + Docker PG           | session 级别（全测试共享）   |
| E2E 测试   | 同集成测试                                | session 级别                 |

### 9.2 测试隔离

- 单元测试：完全 mock，无状态共享
- 集成测试：每个测试使用独立事务 + ROLLBACK，不影响其他测试的数据
- E2E 测试：seed 数据只读，不执行写操作

---

## 10. 覆盖率要求

| 模块                        | 最低行覆盖率 | 最低分支覆盖率 | 理由                          |
| --------------------------- | ------------ | -------------- | ----------------------------- |
| `sql/validator.py`          | 98%          | 95%            | 安全核心，零容忍             |
| `sql/executor.py`           | 90%          | 85%            | 含安全逻辑（脱敏/截断）     |
| `db/pool_manager.py`        | 90%          | 85%            | 熔断器需完整状态机覆盖      |
| `schema/cache.py`           | 90%          | 85%            | 并发/TTL 逻辑复杂           |
| `verification/verifier.py`  | 85%          | 80%            | 策略矩阵需全覆盖            |
| `llm/client.py`             | 85%          | 80%            | 异常路径需覆盖               |
| `llm/schema_retriever.py`   | 90%          | 85%            | 评分/裁剪逻辑               |
| `server.py` (Pipeline)      | 85%          | 80%            | 编排逻辑 + 异常映射         |
| `config.py`                 | 85%          | 80%            | 多数据库解析复杂度           |
| `logging.py`                | 90%          | 85%            | 脱敏逻辑不能遗漏             |
| **整体**                    | **≥ 85%**    | **≥ 80%**      |                               |

---

## 11. CI 集成

### 11.1 CI Pipeline 阶段

```yaml
# .github/workflows/test.yml
jobs:
  lint:
    steps:
      - run: ruff check src/ tests/
      - run: ruff format --check src/ tests/

  typecheck:
    steps:
      - run: mypy src/pg_mcp/

  unit-tests:
    steps:
      - run: pytest -m unit --cov=pg_mcp --cov-branch --cov-fail-under=85

  integration-tests:
    services:
      postgres:
        image: postgres:16-alpine
        env: { POSTGRES_USER: pgmcp_test, ... }
    steps:
      - run: pytest -m integration

  security-tests:
    steps:
      - run: pytest -m security -v
```

### 11.2 触发规则

| 事件         | 运行范围                        |
| ------------ | ------------------------------- |
| PR 创建/更新 | lint + typecheck + unit-tests   |
| 合并到 main  | 全部（含 integration + E2E）    |
| 定时（每日） | 全部                            |

---

## 12. 测试用例总览统计

| 模块                    | 单元 | 集成 | E2E | 安全 | 性能 | 合计  |
| ----------------------- | ---- | ---- | --- | ---- | ---- | ----- |
| 配置 (config)           | 10   | —    | —   | 1    | —    | 11    |
| 数据模型 (models)       | 8    | —    | —   | —    | —    | 8     |
| 错误体系 (errors)       | 5    | —    | —   | —    | —    | 5     |
| 日志脱敏 (logging)      | 10   | —    | —   | 8    | —    | 10    |
| SQL 校验 (validator)    | 65   | —    | —   | 65   | 1    | 66    |
| 熔断器 (circuit)        | 15   | —    | —   | —    | —    | 15    |
| Schema 缓存 (cache)     | 10   | —    | —   | —    | —    | 10    |
| Schema 检索 (retriever) | 12   | —    | —   | —    | 1    | 13    |
| Prompt 模板 (prompts)   | 8    | —    | —   | —    | —    | 8     |
| LLM 客户端 (client)     | 11   | —    | —   | —    | —    | 11    |
| 语义验证 (verifier)     | 13   | —    | —   | —    | —    | 13    |
| Pipeline 逻辑           | 19   | —    | —   | 2    | —    | 19    |
| SQL 执行器 (executor)   | —    | 17   | —   | 6    | 2    | 19    |
| Schema 采集 (collector) | —    | 12   | —   | —    | —    | 12    |
| 连接池管理 (pool)       | —    | 5    | —   | —    | 1    | 6     |
| Pipeline 集成           | —    | 5    | —   | 1    | —    | 5     |
| 端到端                  | —    | —    | 10  | 1    | —    | 10    |
| **合计**                | **186** | **39** | **10** | **84** | **5** | **~235** |

> 注：安全列为与安全相关测试的统计（与其他列有重叠），总计取各模块合计列之和。

---

## 13. 需求追踪矩阵

| PRD 需求               | 关键测试用例                          | 测试层级      |
| ---------------------- | ------------------------------------- | ------------- |
| FR-2.1.1-01 启动连接   | IP1, IP2                              | 集成          |
| FR-2.1.1-02 懒加载     | S1, S2, IT4, IT5                      | 单元+集成     |
| FR-2.1.1-03 元数据采集  | IS1-IS9                              | 集成          |
| FR-2.1.1-05 启动容错   | IP2, S9                               | 集成+单元     |
| FR-2.1.1-06 权限降级   | IS12                                  | 集成          |
| FR-2.2.2-02 检索增强   | R1-R12                                | 单元          |
| FR-2.2.2-03 Prompt 模板| P1-P8                                 | 单元          |
| FR-2.2.2-04 数据库推断  | PL3-PL6                              | 单元          |
| FR-2.2.2-05 LLM不可信  | V30-V106, PL7-PL8                     | 单元          |
| FR-2.3-01 AST 解析     | V01-V21                               | 单元          |
| FR-2.3-02 单语句       | V50, V51                              | 单元          |
| FR-2.3-03 白名单       | V01-V21, V59-V63                      | 单元          |
| FR-2.3-04 黑名单       | V30-V42, V50-V54                      | 单元          |
| FR-2.3-05 函数黑名单   | V70-V106                              | 单元          |
| FR-2.3-06 超长拒绝     | V17, V55                              | 单元          |
| FR-2.3-07 不返回SQL    | PL8, E8                               | 单元+E2E      |
| FR-2.4-02 只读事务     | IE1, IE2, IE17                         | 集成          |
| FR-2.4-03 连接池       | IP1-IP5, PL12                          | 集成+单元     |
| FR-2.4-04 结果限制     | IE7-IE11, E5                           | 集成+E2E      |
| FR-2.4-05 错误脱敏     | IE12-IE14                              | 集成          |
| FR-2.5-01 验证默认关   | VF1, VF2                               | 单元          |
| FR-2.5-02 双模式       | VF4, VF6, VF7-VF9                      | 单元          |
| FR-2.5-05 重试机制     | PL15-PL18                              | 单元          |
| FR-2.6-01 返回模式     | PL1, PL2, E1, E4                       | 单元+E2E      |
| FR-2.6-04 错误格式     | PL13, PL14                             | 单元          |
| NFR-4.1.2 凭据保护     | C5, L1-L3                              | 单元          |
| NFR-4.3-04 熔断        | B1-B15                                 | 单元          |
| NFR-4.4-03 日志红线    | L1-L8                                  | 单元          |

---

## 14. 风险与依赖

| 风险                                  | 影响   | 缓解措施                                       |
| ------------------------------------- | ------ | ---------------------------------------------- |
| Docker PG 在 CI 不可用                | Medium | 集成/E2E 测试标记 marker，可独立跳过            |
| SQLGlot 版本升级改变 AST 结构         | High   | 锁定 sqlglot 版本；V110-V113 作为回归保护      |
| DeepSeek API 在测试中不可调用         | Low    | 全部使用 mock；仅手动冒烟测试调用真实 API      |
| asyncpg `prepare().get_attributes()` API 变化 | Medium | IE16 集成测试作为回归保护          |
| 测试种子数据与 PG 版本不兼容          | Low    | 固定 PG 16；seed.sql 使用标准 SQL              |
