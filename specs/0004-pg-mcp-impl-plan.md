# IMPL-0004: pg-mcp 实现计划

| 字段       | 值                          |
| ---------- | --------------------------- |
| 文档编号   | IMPL-0004                   |
| 关联设计   | DES-0002 v0.2               |
| 关联 PRD   | PRD-0001 v0.2               |
| 版本       | 0.1 (Draft)                 |
| 创建日期   | 2026-03-12                  |

---

## 1. 实现原则

- **自底向上构建**：先实现无外部依赖的底层模块，逐层向上组装，确保每一层可独立测试
- **安全优先**：SQL Validator 作为最关键安全组件，在 Phase 2 率先实现并充分测试
- **每个 Phase 自含验证**：每阶段结束时有可运行的测试套件证明该阶段正确性
- **增量可运行**：Phase 5 结束即可启动一个功能最小但完整的 MCP server
- **无 mock 不上层**：上层模块对下层依赖通过接口/协议隔离，方便 mock 测试

---

## 2. 依赖图

```
Phase 1: 基础骨架
  config.py ─── models.py ─── errors.py ─── logging.py
       │
       ▼
Phase 2: SQL 安全校验 ──────────────────────────────────┐
  sql/validator.py                                       │
       │                                                 │
       ▼                                                 │
Phase 3: 数据库层                                        │
  db/pool_manager.py ── sql/executor.py                  │
       │                     │                           │
       ▼                     │                           │
Phase 4: Schema 层           │                           │
  schema/collector.py        │                           │
  schema/cache.py            │                           │
       │                     │                           │
       ▼                     │                           │
Phase 5: LLM 层              │                           │
  llm/client.py              │                           │
  llm/prompts.py             │                           │
  llm/schema_retriever.py    │                           │
       │                     │                           │
       ▼                     ▼                           │
Phase 6: 验证层                                          │
  verification/verifier.py                               │
       │                                                 │
       ▼                                                 │
Phase 7: 服务器编排 ◄────────────────────────────────────┘
  server.py (QueryPipeline + FastMCP tool + lifespan)
  __main__.py
       │
       ▼
Phase 8: 集成测试 & 文档
  E2E 测试 + README + .env.example
       │
       ▼
Phase 9: 多数据库安全控制
  config.py (per-db security)
  sql/validator.py (table whitelist/blacklist)
  sql/executor.py (per-db search_path)
  server.py (per-db executor selection)
       │
       ▼
Phase 10: 弹性与可观测性
  llm/client.py (retry + backoff)
  middleware/rate_limiter.py
  middleware/metrics.py
  server.py (metrics integration)
       │
       ▼
Phase 11: 模型清理与测试覆盖增强
  config.py / models.py / schema/models.py (cleanup)
  tests/* (coverage > 90%)
```

---

## 3. 分阶段实现计划

### Phase 1: 项目骨架与基础模块

**目标**：建立项目结构、依赖管理、配置加载、数据模型、错误体系、日志系统。此阶段完成后所有后续模块有稳定的基础可依赖。

**创建文件（按顺序）：**

| #  | 文件                              | 内容                                                  | 设计文档参照    |
| -- | --------------------------------- | ----------------------------------------------------- | --------------- |
| 1  | `pyproject.toml`                  | 项目元数据、全部依赖（含 dev）、构建配置              | §9              |
| 2  | `src/pg_mcp/__init__.py`          | 包初始化，暴露 `__version__`                          | —               |
| 3  | `src/pg_mcp/config.py`            | `DatabaseConfig`, `LLMConfig`, `ServerConfig`         | §3              |
|    |                                   | 数据库别名解析逻辑（`PG_MCP_DATABASES` → 各别名配置） |                 |
| 4  | `src/pg_mcp/errors.py`            | 自定义异常层级：`PgMcpError` 基类                     | §7              |
|    |                                   | `ValidationError`, `ExecutionError`, `LLMError`,      |                 |
|    |                                   | `LLMParseError`, `CircuitOpenError`,                  |                 |
|    |                                   | `AmbiguousDBError`, `RateLimitError`                  |                 |
| 5  | `src/pg_mcp/models.py`            | 请求/响应 Pydantic 模型：`QueryRequest`,              | §4.2            |
|    |                                   | `QueryResult`, `QueryResponse`, `ErrorDetail` 等      |                 |
| 6  | `src/pg_mcp/schema/models.py`     | Schema 数据模型：`ColumnInfo`, `TableInfo`,            | §4.1            |
|    |                                   | `DatabaseSchema`, `EnumTypeInfo` 等                   |                 |
| 7  | `src/pg_mcp/logging.py`           | `configure_logging()`, `sanitize_processor`            | §5.9            |
| 8  | 所有包的 `__init__.py`            | `schema/`, `llm/`, `sql/`, `verification/`, `db/`     | §2              |

**验收标准：**
- `pip install -e ".[dev]"` 成功安装
- `python -c "from pg_mcp.config import ServerConfig"` 无报错
- 单元测试 `test_config.py`：验证环境变量解析、默认值、多数据库别名解析、`SecretStr` 不泄露
- 单元测试 `test_models.py`：验证 Pydantic 模型序列化/反序列化、枚举值、可选字段

**预估工时**：0.5 天

---

### Phase 2: SQL 安全校验器

**目标**：实现 SQLGlot AST 级别的 SQL 安全校验器。这是整个系统最关键的安全组件，必须有最高的测试覆盖率。

**创建文件：**

| #  | 文件                              | 内容                                                  | 设计文档参照    |
| -- | --------------------------------- | ----------------------------------------------------- | --------------- |
| 1  | `src/pg_mcp/sql/__init__.py`      | 包初始化                                              | —               |
| 2  | `src/pg_mcp/sql/validator.py`     | `SQLValidator` 类                                     | §5.6            |
|    |                                   | - `validate(sql) → exp.Expression`                    |                 |
|    |                                   | - SQL 长度检查                                        |                 |
|    |                                   | - `sqlglot.parse()` + 单语句检查                      |                 |
|    |                                   | - 根节点白名单 (`Select`, `Union`, `Intersect`, `Except`) |              |
|    |                                   | - EXPLAIN 处理（默认禁止 ANALYZE）                    |                 |
|    |                                   | - AST walk：黑名单语句类型 + SELECT INTO + 危险函数   |                 |
|    |                                   | - `DEFAULT_BLOCKED_FUNCTIONS` 完整集合（30+）         |                 |

**关键实现细节：**
- `sqlglot.parse(sql, dialect="postgres")` 解析为 AST
- 白名单使用 `isinstance(ast, (exp.Select, exp.Union, ...))` 检查
- 函数检查遍历 AST 所有节点：`isinstance(node, (exp.Anonymous, exp.Func))`
- 黑名单函数名统一小写比较

**测试文件：`tests/test_validator.py`**

必须覆盖设计文档 §10 中的 **全部 22 个测试用例**：

```
合法 SELECT / CTE / UNION / 多语句 / INSERT / UPDATE / DELETE / CREATE /
SELECT INTO / CTE+INSERT / pg_sleep / dblink / lo_export / EXPLAIN /
EXPLAIN ANALYZE / 超长 SQL / COPY / SET / Advisory lock / Notify /
Replication / File read
```

**额外补充测试用例（从设计 review 中识别的边界情况）：**
- 嵌套子查询中的危险函数：`SELECT * FROM (SELECT pg_sleep(1)) t`
- CTE 体为 INSERT：`WITH t AS (INSERT INTO x VALUES(1) RETURNING *) SELECT * FROM t`
- 函数名大小写混合：`SELECT PG_SLEEP(1)`
- 注释中包含危险内容：`SELECT 1 -- pg_sleep(100)`
- 空字符串 / NULL 输入
- 恰好 10000 字符的 SQL（边界值）

**验收标准：**
- 全部 28+ 测试用例通过
- 测试覆盖率 > 95%
- `ruff check` 零警告

**预估工时**：1 天

---

### Phase 3: 数据库连接池与执行器

**目标**：实现连接池管理（含熔断器）和只读 SQL 执行器。

**创建文件：**

| #  | 文件                              | 内容                                                  | 设计文档参照    |
| -- | --------------------------------- | ----------------------------------------------------- | --------------- |
| 1  | `src/pg_mcp/db/__init__.py`       | 包初始化                                              | —               |
| 2  | `src/pg_mcp/db/pool_manager.py`   | `CircuitState`, `DatabasePool`, `PoolManager`         | §5.3            |
|    |                                   | - 连接池创建 `asyncpg.create_pool()`                  |                 |
|    |                                   | - 熔断器完整状态机                                    |                 |
|    |                                   |   CLOSED → OPEN → HALF_OPEN → CLOSED/OPEN             |                 |
|    |                                   | - `CIRCUIT_TRIPPING_ERRORS` 定义                      |                 |
|    |                                   | - `_half_open_lock` 单请求试探                        |                 |
|    |                                   | - `PoolManager.initialize()` / `close()`              |                 |
|    |                                   | - `Semaphore` 全局并发限制                            |                 |
| 3  | `src/pg_mcp/sql/executor.py`      | `SQLExecutor`                                         | §5.7            |
|    |                                   | - `execute_readonly(pool, sql, max_rows)`             |                 |
|    |                                   | - `transaction(readonly=True)` + SET LOCAL            |                 |
|    |                                   | - `SET LOCAL search_path` 白名单                      |                 |
|    |                                   | - `conn.prepare()` + `prepared.get_attributes()`      |                 |
|    |                                   | - `prepared.fetch(max_rows + 1)` 行数限制             |                 |
|    |                                   | - `_truncate_fields()` 多类型截断                     |                 |
|    |                                   | - `_estimate_payload_size()` + payload 裁剪            |                 |
|    |                                   | - `_sanitize_error()` 多层脱敏                        |                 |

**测试策略：**

| 文件                         | 类型       | 方法                                          |
| ---------------------------- | ---------- | --------------------------------------------- |
| `tests/test_circuit.py`      | 单元测试   | Mock `asyncpg.Pool`，验证熔断状态转换         |
|                              |            | - 连续 5 次失败 → OPEN                        |
|                              |            | - 等待 recovery_timeout → HALF_OPEN           |
|                              |            | - 试探成功 → CLOSED                           |
|                              |            | - 试探失败 → OPEN（重置计时器）               |
|                              |            | - 非熔断错误不影响计数                        |
| `tests/test_executor.py`     | 集成测试   | Docker PostgreSQL                             |
|                              |            | - 只读事务（写操作应被 PG 拒绝）              |
|                              |            | - statement_timeout 触发                       |
|                              |            | - search_path 限制生效                         |
|                              |            | - 空结果集的列元数据正确                       |
|                              |            | - 字段截断（str/bytes/json/array）             |
|                              |            | - payload 大小裁剪                             |
|                              |            | - 错误脱敏（不含表名/DETAIL/HINT）            |

**前置依赖**：Phase 1（config, models, errors）

**验收标准：**
- 熔断器单元测试全部通过
- 集成测试在 Docker PG 上通过（如无 Docker 则标记 skip）
- `ruff check` 零警告

**预估工时**：1.5 天

---

### Phase 4: Schema 采集与缓存

**目标**：实现数据库元数据采集、内存缓存（含 TTL 和懒加载）。

**创建文件：**

| #  | 文件                              | 内容                                                  | 设计文档参照    |
| -- | --------------------------------- | ----------------------------------------------------- | --------------- |
| 1  | `src/pg_mcp/schema/collector.py`  | `SchemaCollector`                                     | §5.4.1          |
|    |                                   | - `TABLES_QUERY`, `COLUMNS_QUERY`,                    |                 |
|    |                                   |   `FOREIGN_KEYS_QUERY`, `INDEXES_QUERY`,              |                 |
|    |                                   |   `ENUM_TYPES_QUERY`, `VIEW_DEFINITIONS_QUERY`        |                 |
|    |                                   | - `collect_full(conn) → DatabaseSchema`               |                 |
|    |                                   | - `collect_summary(conn) → dict`                      |                 |
|    |                                   | - `_assemble()` 将原始行组装为 Pydantic 模型          |                 |
|    |                                   | - 权限降级：try/except per query, log warning         |                 |
| 2  | `src/pg_mcp/schema/cache.py`      | `CacheEntry`, `SchemaCache`                           | §5.4.2          |
|    |                                   | - `warm_up(pool_manager)` 启动摘要采集                |                 |
|    |                                   | - `get_or_load(alias, pool_manager)` 懒加载+TTL       |                 |
|    |                                   | - `refresh(alias, pool_manager)` 强制刷新             |                 |
|    |                                   | - `list_databases()` 返回摘要列表                     |                 |
|    |                                   | - `max_tables_per_db` 截断保护                        |                 |
|    |                                   | - `asyncio.Lock` 防并发加载                           |                 |

**Schema 采集 SQL 查询实现要点：**

```
INDEXES_QUERY:
  pg_catalog.pg_indexes → index_name, tablename, indexdef
  解析 indexdef 提取列名和索引类型

ENUM_TYPES_QUERY:
  pg_catalog.pg_type + pg_catalog.pg_enum
  WHERE typtype = 'e'

VIEW_DEFINITIONS_QUERY:
  information_schema.views → view_definition
  （配置开关控制是否采集）

PRIMARY_KEY_QUERY:
  information_schema.table_constraints + key_column_usage
  WHERE constraint_type = 'PRIMARY KEY'

TABLE_COMMENTS_QUERY:
  pg_catalog.pg_description + pg_catalog.pg_class
  WHERE objsubid = 0

ROW_ESTIMATES_QUERY:
  pg_catalog.pg_class → reltuples
```

**测试文件：**

| 文件                             | 类型       | 方法                                          |
| -------------------------------- | ---------- | --------------------------------------------- |
| `tests/test_schema_cache.py`     | 单元测试   | Mock collector, 验证 TTL 过期、懒加载、       |
|                                  |            | 并发锁、截断警告、刷新                        |
| `tests/test_schema_collector.py` | 集成测试   | Docker PG + 预建 schema                       |
|                                  |            | - 采集表/列/外键/索引/枚举/注释               |
|                                  |            | - 权限不足时优雅降级                           |
|                                  |            | - 空数据库                                     |

**前置依赖**：Phase 1 + Phase 3（pool_manager）

**验收标准：**
- 缓存单元测试全部通过（TTL、懒加载、并发、截断）
- 集成测试在 Docker PG 上通过

**预估工时**：1 天

---

### Phase 5: LLM 交互层

**目标**：实现 DeepSeek/OpenAI API 调用封装、prompt 模板、schema 检索增强。

**创建文件：**

| #  | 文件                              | 内容                                                  | 设计文档参照    |
| -- | --------------------------------- | ----------------------------------------------------- | --------------- |
| 1  | `src/pg_mcp/llm/client.py`       | `LLMClient`                                           | §5.5.1          |
|    |                                   | - `AsyncOpenAI(base_url=deepseek)`                    |                 |
|    |                                   | - `chat(system, user, max_tokens) → str`              |                 |
|    |                                   | - 异常捕获 → `LLMError` / `LLMParseError`            |                 |
| 2  | `src/pg_mcp/llm/prompts.py`      | Prompt 模板常量                                       | §5.5.2          |
|    |                                   | - `SQL_GENERATION_SYSTEM` / `SQL_GENERATION_USER`     |                 |
|    |                                   | - `VERIFICATION_SYSTEM_METADATA`                      |                 |
|    |                                   | - `DB_SELECTION_SYSTEM`                                |                 |
|    |                                   | - `build_sql_generation_prompt(question, schema_ctx)` |                 |
|    |                                   | - `build_verification_prompt(...)`                     |                 |
|    |                                   | - `build_db_selection_prompt(question, summaries)`     |                 |
| 3  | `src/pg_mcp/llm/schema_retriever.py` | `SchemaRetriever`                                  | §5.5.3          |
|    |                                   | - `find_relevant_tables(question, schema) → list`     |                 |
|    |                                   | - `_tokenize(question) → list[str]`                   |                 |
|    |                                   | - `_score_table(tokens, table) → float`               |                 |
|    |                                   | - `render_schema_context(tables) → str`               |                 |
|    |                                   | - 字符预算裁剪逻辑                                    |                 |

**LLM 响应解析实现要点：**
- 从 LLM 响应中提取 SQL：去除 markdown 代码块围栏（如有）、去除解释文字
- 提取逻辑：正则匹配 ` ```sql...``` ` 块，或取整个响应作为 SQL
- 如果提取失败，抛出 `LLMParseError`

**测试文件：**

| 文件                               | 类型       | 方法                                          |
| ---------------------------------- | ---------- | --------------------------------------------- |
| `tests/test_schema_retriever.py`   | 单元测试   | 构造模拟 `DatabaseSchema`                     |
|                                    |            | - 精确表名匹配得分最高                        |
|                                    |            | - 列名/注释匹配                               |
|                                    |            | - 字符预算裁剪（超预算时截断）                |
|                                    |            | - 零匹配时 fallback 到前 10 表                |
|                                    |            | - `render_schema_context()` 格式正确          |
| `tests/test_prompts.py`            | 单元测试   | 模板渲染、占位符替换、长度控制                |
| `tests/test_llm_client.py`         | 单元测试   | Mock `AsyncOpenAI`                            |
|                                    |            | - 正常响应解析                                |
|                                    |            | - API 错误 → `LLMError`                       |
|                                    |            | - 非法响应 → `LLMParseError`                  |
|                                    |            | - markdown 代码块提取                          |

**前置依赖**：Phase 1（config, models） + Phase 4（schema models 用于测试）

**验收标准：**
- SchemaRetriever 单元测试全部通过
- LLMClient 带 mock 测试全部通过
- Prompt 模板测试通过

**预估工时**：1 天

---

### Phase 6: 语义验证层

**目标**：实现可选的结果语义验证，含 verify_mode/verify_result 交互策略。

**创建文件：**

| #  | 文件                              | 内容                                                  | 设计文档参照    |
| -- | --------------------------------- | ----------------------------------------------------- | --------------- |
| 1  | `src/pg_mcp/verification/verifier.py` | `ResultVerifier`                                 | §5.8            |
|    |                                   | - `should_verify(request_verify) → bool`              |                 |
|    |                                   | - `verify(question, sql, result) → VerificationResult`|                 |
|    |                                   | - `_build_metadata_context(result) → str`             |                 |
|    |                                   | - `_build_sample_context(result) → str`               |                 |
|    |                                   | - `_parse_verification(response) → VerificationResult`|                 |
|    |                                   | - JSON 响应解析（含容错）                             |                 |

**测试文件：`tests/test_verifier.py`**

| 场景                           | 方法                                                  |
| ------------------------------ | ----------------------------------------------------- |
| `verify_mode=off` + any        | `should_verify()` 返回 False                          |
| `verify_mode=metadata` + true  | `should_verify()` 返回 True，调用 metadata 模式       |
| `verify_mode=metadata` + false | `should_verify()` 返回 False                          |
| `verify_mode=sample` + true    | `should_verify()` 返回 True，调用 sample 模式         |
| metadata context 构建          | 验证输出格式包含列名、行数、truncated                 |
| sample context 构建            | 验证行数不超过 verify_sample_rows                     |
| LLM 返回非法 JSON              | 容错处理，返回 `match="unknown"`                      |

**前置依赖**：Phase 1 + Phase 5（LLMClient）

**验收标准：**
- 策略矩阵 6 种组合全部测试通过
- LLM 响应解析容错测试通过

**预估工时**：0.5 天

---

### Phase 7: 服务器编排与入口

**目标**：实现 FastMCP server、QueryPipeline 编排器、`__main__.py` 入口。这是所有模块的集成点。

**创建文件：**

| #  | 文件                              | 内容                                                  | 设计文档参照    |
| -- | --------------------------------- | ----------------------------------------------------- | --------------- |
| 1  | `src/pg_mcp/server.py`           | 完整实现                                               | §5.1, §5.2, §7 |
|    |                                   | **FastMCP 实例:**                                      |                 |
|    |                                   | - `lifespan()` async context manager                   |                 |
|    |                                   |   - 加载 config                                        |                 |
|    |                                   |   - 创建 PoolManager + initialize()                    |                 |
|    |                                   |   - 创建 SchemaCache + warm_up()                       |                 |
|    |                                   |   - 创建 LLMClient                                     |                 |
|    |                                   |   - yield 资源 dict                                    |                 |
|    |                                   |   - 清理：pool_manager.close()                         |                 |
|    |                                   | - `@mcp.tool` query_tool() 入口                        |                 |
|    |                                   |                                                        |                 |
|    |                                   | **QueryPipeline:**                                     |                 |
|    |                                   | - `execute(request) → QueryResponse`                   |                 |
|    |                                   | - Stage 1: `resolve_database()`                        |                 |
|    |                                   |   - 本地匹配 `_match_database_local()`                 |                 |
|    |                                   |   - LLM 辅助 `_match_database_llm()`                   |                 |
|    |                                   | - Stage 2: `ensure_schema_loaded()`                    |                 |
|    |                                   | - Stage 3: `generate_sql()`                            |                 |
|    |                                   |   - schema_retriever.find_relevant_tables()            |                 |
|    |                                   |   - prompts.build_sql_generation_prompt()              |                 |
|    |                                   |   - llm_client.chat() → 提取 SQL                       |                 |
|    |                                   | - Stage 4: `validate_sql()`                            |                 |
|    |                                   | - Stage 5: [sql 模式] 直接返回                         |                 |
|    |                                   | - Stage 6: `execute_sql()`                             |                 |
|    |                                   | - Stage 7: [可选] `verify_result()` + 重试逻辑         |                 |
|    |                                   | - Stage 8: `build_response()`                          |                 |
|    |                                   | - `EXCEPTION_MAP` 统一异常处理                         |                 |
|    |                                   | - `_current_stage` 追踪当前阶段                        |                 |
|    |                                   | - structlog 每阶段记录耗时                             |                 |
| 2  | `src/pg_mcp/__main__.py`         | 入口点                                                 | §11             |
|    |                                   | - `python -m pg_mcp`                                   |                 |
|    |                                   | - 解析 `--transport` (stdio/sse) 和 `--port` 参数      |                 |
|    |                                   | - 调用 `mcp.run()`                                     |                 |

**QueryPipeline 内部数据库匹配逻辑：**

```
_match_database_local(question, summaries):
  1. 提取 question 中的关键词
  2. 对每个数据库的 table 名列表计算命中率
  3. 如果有唯一最高分且 > 阈值 → 返回该数据库
  4. 否则返回 None（交给 LLM 判断）

_match_database_llm(question, summaries):
  1. 构建 DB_SELECTION_SYSTEM prompt
  2. 调用 llm_client.chat()
  3. 解析响应为数据库别名
  4. 如果别名不在已知列表中 → 抛出 AmbiguousDBError
```

**验证重试逻辑：**

```
max_retries = 2
for attempt in range(max_retries + 1):
    result = execute_sql(sql)
    if not should_verify:
        break
    verification = verify(question, sql, result)
    if verification.match == "yes" or attempt == max_retries:
        break
    if verification.suggested_sql:
        new_sql = verification.suggested_sql
        validate_sql(new_sql)  # 重试的 SQL 也必须过校验
        sql = new_sql
    else:
        break
```

**测试文件：**

| 文件                         | 类型       | 方法                                          |
| ---------------------------- | ---------- | --------------------------------------------- |
| `tests/test_pipeline.py`     | 集成测试   | Mock LLM + Mock PG                            |
|                              |            | - 完整 result 模式流程                        |
|                              |            | - sql 模式（不执行）                          |
|                              |            | - 数据库自动推断（本地匹配）                  |
|                              |            | - 数据库自动推断（LLM 辅助）                  |
|                              |            | - 安全校验失败处理                            |
|                              |            | - LLM 错误处理                                |
|                              |            | - 执行错误处理                                |
|                              |            | - 验证重试逻辑（最多 2 次）                   |
|                              |            | - 并发限制触发                                |
| `tests/test_server.py`       | E2E        | FastMCP test client                           |
|                              |            | - tool 注册正确                               |
|                              |            | - lifespan 启动/关闭                          |

**前置依赖**：Phase 1 ~ Phase 6（全部）

**验收标准：**
- `python -m pg_mcp` 启动无报错（需配置环境变量）
- Pipeline 集成测试全部通过
- 能从 Cursor MCP 客户端成功调用 query tool

**预估工时**：2 天

---

### Phase 8: 端到端测试与文档

**目标**：完整 E2E 验证、编写用户文档、准备 .env 示例。

**创建/更新文件：**

| #  | 文件                              | 内容                                                  |
| -- | --------------------------------- | ----------------------------------------------------- |
| 1  | `README.md`                       | 项目说明、快速开始、配置参考、部署指南                |
| 2  | `.env.example`                    | 全部环境变量示例（含注释）                            |
| 3  | `tests/test_e2e.py`              | 端到端测试（Docker PG + Mock LLM）                    |
|    |                                   | - 自然语言 → SQL → 执行 → 结果返回                   |
|    |                                   | - 错误场景全覆盖                                      |
| 4  | `tests/conftest.py`              | 共享 fixtures：PG 容器、mock LLM、配置                |
| 5  | `tests/docker-compose.yml`       | 测试用 PostgreSQL 容器定义                            |
| 6  | `tests/fixtures/seed.sql`        | 测试数据库初始化脚本（建表 + 插入示例数据）           |

**E2E 测试场景：**

| #  | 场景                                         | 验证点                                |
| -- | -------------------------------------------- | ------------------------------------- |
| 1  | 简单查询：「查询所有用户」                   | 返回正确行数和列结构                  |
| 2  | 聚合查询：「每个部门有多少人」               | GROUP BY + COUNT 结果正确             |
| 3  | JOIN 查询：「用户及其订单」                   | 多表关联结果正确                      |
| 4  | sql 模式：「显示查询所有用户的 SQL」         | 仅返回 SQL，不执行                    |
| 5  | 大结果集截断                                 | truncated=true，行数=max_rows         |
| 6  | 空结果集                                     | rows=[]，columns 仍有值              |
| 7  | 不存在的数据库                               | DB_UNAVAILABLE 错误                   |
| 8  | LLM 生成危险 SQL（模拟）                     | VALIDATION_FAILED 错误                |

**前置依赖**：Phase 7

**验收标准：**
- E2E 测试全部通过
- README 内容完整、可跟随操作
- `ruff check` + `mypy --strict` 零错误

**预估工时**：1 天

---

### Phase 9: 多数据库安全控制

**目标**：实现 per-database 安全策略，每个数据库配置独立的表/列访问白名单和 EXPLAIN 策略，确保请求只能访问授权的数据库与对象。

**背景**：当前服务器使用单一 `SQLExecutor`，所有数据库共享相同的 `allowed_schemas` 和安全配置，无法对不同数据库施加差异化的访问限制。

**创建/更新文件：**

| #  | 文件                              | 内容                                                  |
| -- | --------------------------------- | ----------------------------------------------------- |
| 1  | `src/pg_mcp/config.py`            | 扩展 `DatabaseConfig` 增加 per-db 安全字段：          |
|    |                                   | - `allowed_schemas: list[str]`（覆盖全局值）          |
|    |                                   | - `allowed_tables: list[str] \| None`（白名单）       |
|    |                                   | - `denied_tables: list[str] \| None`（黑名单）        |
|    |                                   | - `allow_explain: bool = False`                       |
|    |                                   | - `max_rows_override: int \| None`                    |
| 2  | `src/pg_mcp/sql/executor.py`      | 创建 per-db `SQLExecutor` 实例或注入 per-db config：  |
|    |                                   | - `search_path` 由 per-db `allowed_schemas` 控制      |
|    |                                   | - 执行前校验 SQL 涉及的表是否在白名单内               |
| 3  | `src/pg_mcp/sql/validator.py`     | 增加 `allow_explain` 参数，per-db 可选启用 EXPLAIN    |
|    |                                   | - 增加 `table_whitelist` / `table_blacklist` AST 检查 |
| 4  | `src/pg_mcp/server.py`            | `QueryPipeline` 在 resolve_database 后，              |
|    |                                   | 根据 database alias 获取对应的安全策略，               |
|    |                                   | 创建/选择匹配的 validator + executor                  |

**测试文件：`tests/test_db_security.py`**

| 场景                             | 验证点                                        |
| -------------------------------- | --------------------------------------------- |
| db-A 允许 public.users，db-B 不允许 | 跨库访问被拒绝                              |
| per-db allowed_schemas 生效      | search_path 仅包含配置的 schema               |
| per-db allow_explain=true        | EXPLAIN 可用；其他 db 仍被拒绝               |
| table_whitelist 限制             | 访问白名单外的表返回 VALIDATION_FAILED       |
| table_blacklist 限制             | 访问黑名单内的表返回 VALIDATION_FAILED       |

**验收标准：**
- 每个数据库可配置独立安全策略
- 不同数据库的访问控制互不干扰
- 全部安全场景测试通过

**预估工时**：1.5 天

---

### Phase 10: 弹性与可观测性

**目标**：将速率限制、重试/退避机制、指标/追踪系统从设计层面落地到实际请求处理流程中。

**背景**：当前代码有 `RateLimitError` 异常类和 circuit breaker，但缺少 LLM 调用重试、请求级速率限制、以及结构化指标收集。

**创建/更新文件：**

| #  | 文件                              | 内容                                                  |
| -- | --------------------------------- | ----------------------------------------------------- |
| 1  | `src/pg_mcp/llm/client.py`       | 增加重试/退避机制：                                   |
|    |                                   | - 指数退避（base=1s, max=30s, jitter）               |
|    |                                   | - 可重试异常：429 RateLimit、5xx Server Error         |
|    |                                   | - 最大重试次数可配置（默认 3）                        |
|    |                                   | - 每次重试记录 structlog 日志                         |
| 2  | `src/pg_mcp/middleware/`          | 新建中间件包：                                        |
|    | `rate_limiter.py`                 | - 基于 token-bucket 或 sliding-window 的速率限制      |
|    |                                   | - 配置项：`PG_MCP_RATE_LIMIT_RPM`（默认 60）         |
|    |                                   | - 超限时返回 `RateLimitError`                         |
| 3  | `src/pg_mcp/middleware/`          |                                                       |
|    | `metrics.py`                      | 结构化指标收集：                                      |
|    |                                   | - 请求计数（按 database / stage / status）            |
|    |                                   | - 各阶段耗时（generate_sql / execute / verify）       |
|    |                                   | - LLM 调用次数与延迟                                  |
|    |                                   | - 活跃连接数 / 连接池使用率                           |
|    |                                   | - 熔断器状态变更事件                                  |
|    |                                   | - 通过 structlog 输出 JSON 格式指标                   |
| 4  | `src/pg_mcp/server.py`            | - Pipeline 各阶段计时并记录指标                       |
|    |                                   | - lifespan 中初始化 rate_limiter                      |
|    |                                   | - query_tool 入口处执行速率限制检查                   |
| 5  | `src/pg_mcp/config.py`            | 增加配置字段：                                        |
|    |                                   | - `rate_limit_rpm: int = 60`                          |
|    |                                   | - `llm_max_retries: int = 3`                          |
|    |                                   | - `llm_retry_base_delay: float = 1.0`                 |
|    |                                   | - `metrics_enabled: bool = True`                      |

**测试文件：**

| 文件                              | 场景                                          |
| --------------------------------- | --------------------------------------------- |
| `tests/test_rate_limiter.py`      | 超过 RPM → RateLimitError；窗口过后恢复       |
| `tests/test_llm_retry.py`        | 429 → 自动重试并成功；超过最大次数 → 报错     |
| `tests/test_metrics.py`          | 指标在请求后正确累计                          |

**验收标准：**
- LLM 调用 429/5xx 时自动重试，指数退避
- 请求级速率限制可用且可配置
- 各阶段耗时指标通过 structlog 输出
- 全部测试通过

**预估工时**：2 天

---

### Phase 11: 模型清理与测试覆盖增强

**目标**：修复 response/model 层缺陷，清理未使用的配置字段，提升测试覆盖率至 >90%。

**背景**：当前存在未使用的配置字段、模型序列化存在 `model_dump` 与 `exclude_none` 行为不一致、部分模块测试覆盖不足。

**更新文件：**

| #  | 文件                              | 内容                                                  |
| -- | --------------------------------- | ----------------------------------------------------- |
| 1  | `src/pg_mcp/config.py`            | - 审计所有配置字段，移除确认未使用的字段              |
|    |                                   | - 为 `access_token` 加上 `@deprecated` 注释或移入      |
|    |                                   |   per-db config（Phase 9 已处理安全）                 |
|    |                                   | - 确保 `env_file=".env"` 在所有 Settings 类一致       |
| 2  | `src/pg_mcp/models.py`            | - 确保 `QueryResponse.model_dump(exclude_none=True)`   |
|    |                                   |   行为在所有场景下一致                                |
|    |                                   | - 增加 `model_config` 统一 JSON 序列化策略             |
|    |                                   | - 清理冗余字段或方法                                  |
| 3  | `src/pg_mcp/schema/models.py`     | - 审查 Pydantic 模型的序列化一致性                    |
| 4  | `tests/test_config.py`            | - 增加 `.env` 加载测试                                |
|    |                                   | - 增加 per-db config 完整覆盖                         |
| 5  | `tests/test_executor.py`          | - 增加 LIMIT 子查询包裹逻辑的测试                     |
|    |                                   | - 增加空结果集、大字段截断、payload 裁剪的边界测试    |
| 6  | `tests/test_pipeline.py`          | - 增加多数据库切换场景                                |
|    |                                   | - 增加各种异常路径的覆盖                              |
| 7  | `tests/test_e2e.py`              | - 补充缺失的 E2E 场景测试                             |

**验收标准：**
- 无未使用的配置字段
- 所有 Pydantic 模型的序列化行为一致
- 测试覆盖率 > 90%
- `ruff check` 零警告
- 所有现有测试仍然通过

**预估工时**：1.5 天

---

## 4. 总工期估算

| Phase | 名称               | 预估工时 | 累计  | 里程碑                            |
| ----- | ------------------ | -------- | ----- | --------------------------------- |
| 1     | 项目骨架与基础模块 | 0.5 天   | 0.5   | 项目可安装，配置可加载            |
| 2     | SQL 安全校验器     | 1 天     | 1.5   | 安全核心就绪，22+ 测试用例通过   |
| 3     | 数据库连接池与执行器| 1.5 天  | 3     | 可连接 PG 并执行只读查询         |
| 4     | Schema 采集与缓存  | 1 天     | 4     | 可自动发现数据库结构              |
| 5     | LLM 交互层         | 1 天     | 5     | 可调用 DeepSeek 生成 SQL         |
| 6     | 语义验证层         | 0.5 天   | 5.5   | 可选结果验证功能就绪              |
| 7     | 服务器编排与入口   | 2 天     | 7.5   | **MCP server 可用** ★            |
| 8     | E2E 测试与文档     | 1 天     | 8.5   | **生产就绪** ★                   |
| 9     | 多数据库安全控制   | 1.5 天   | 10    | per-db 访问控制生效               |
| 10    | 弹性与可观测性     | 2 天     | 12    | 重试/限流/指标落地                |
| 11    | 模型清理与测试增强 | 1.5 天   | 13.5  | 覆盖率 >90%，模型一致            |
|       | **合计**           | **13.5 天** |    |                                   |

---

## 5. 风险与缓解

| 风险                                      | 影响  | 缓解措施                                              |
| ----------------------------------------- | ----- | ----------------------------------------------------- |
| SQLGlot 解析不完整（边界 SQL 语法）       | High  | Phase 2 大量边界测试；发现问题时记录为已知限制         |
| asyncpg `prepare()` + `get_attributes()`  | Medium| Phase 3 集成测试验证；fallback 到首行推断              |
| 对不兼容 API 行为                          |       |                                                       |
| DeepSeek API 不稳定/延迟高               | Medium| LLM 调用设超时（10s）；返回 LLM_ERROR + retryable    |
| FastMCP lifespan 与 asyncpg 集成问题      | Medium| Phase 7 率先验证 lifespan 模式；参考官方示例          |
| 大型 schema 超出 LLM 上下文窗口           | Low   | 字符预算裁剪（8000 chars ≈ 2000 tokens）；已知限制    |
| Docker PG 在 CI 环境不可用                | Low   | 集成测试标记 `@pytest.mark.integration`，可单独跳过   |

---

## 6. 实现检查清单

完成每个 Phase 后勾选：

- [x] Phase 1: 项目骨架与基础模块
- [x] Phase 2: SQL 安全校验器（22+ 测试用例通过）
- [x] Phase 3: 数据库连接池与执行器
- [x] Phase 4: Schema 采集与缓存
- [x] Phase 5: LLM 交互层
- [x] Phase 6: 语义验证层
- [x] Phase 7: 服务器编排与入口（MCP server 可启动）
- [x] Phase 8: E2E 测试与文档
- [x] Phase 9: 多数据库安全控制（per-db 表/列白名单、EXPLAIN 策略）
- [x] Phase 10: 弹性与可观测性（LLM 重试退避、速率限制、指标收集）
- [x] Phase 11: 模型清理与测试覆盖增强（覆盖率 >90%）
- [x] 全量 `ruff check` 通过
- [ ] 全量 `mypy` 通过
- [x] 测试覆盖率 > 90%（185 tests passed）
