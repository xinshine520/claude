# DES-0002: PostgreSQL Natural Language Query MCP Server — 技术设计

| 字段       | 值                          |
| ---------- | --------------------------- |
| 文档编号   | DES-0002                    |
| 关联 PRD   | PRD-0001 v0.2               |
| 版本       | 0.2 (Draft, post-review)    |
| 创建日期   | 2026-03-12                  |
| 状态       | 待评审                      |

---

## 1. 技术选型

| 关注点           | 选型                          | 版本      | 选型理由                                                         |
| ---------------- | ----------------------------- | --------- | ---------------------------------------------------------------- |
| MCP 框架         | **FastMCP**                   | ≥ 2.x     | 高层 Pythonic API，装饰器定义 Tool，内置 Pydantic 校验与 lifespan |
| PostgreSQL 驱动  | **asyncpg**                   | ≥ 0.29    | 纯异步、二进制协议、内置连接池、高性能                           |
| SQL 解析         | **SQLGlot**                   | ≥ 26.x   | 无依赖 SQL 解析器，支持 PostgreSQL 方言、AST 遍历与类型检查      |
| 数据模型/校验    | **Pydantic**                  | ≥ 2.x     | 类型安全配置管理、请求/响应模型序列化                            |
| LLM 客户端       | **openai** (Python SDK)       | ≥ 1.x     | DeepSeek 兼容 OpenAI API，直接使用官方 SDK 设置 base_url        |
| 异步运行时       | **asyncio** (stdlib)          | —         | FastMCP 与 asyncpg 均基于 asyncio                                |
| 日志             | **structlog**                 | ≥ 24.x   | 结构化日志，支持 JSON 输出、处理器链（脱敏过滤器）               |
| 配置             | **pydantic-settings**         | ≥ 2.x     | 环境变量 → Pydantic model 自动映射                               |

---

## 2. 项目结构

```
pg-mcp/
├── pyproject.toml                  # 项目元数据与依赖
├── README.md
├── .env.example                    # 环境变量示例
├── src/
│   └── pg_mcp/
│       ├── __init__.py
│       ├── __main__.py             # 入口：python -m pg_mcp
│       ├── server.py               # FastMCP 实例 & lifespan & tool 注册
│       ├── config.py               # Pydantic Settings 配置模型
│       ├── models.py               # 请求/响应 Pydantic 模型
│       ├── errors.py               # 统一错误码 & 异常类
│       ├── schema/
│       │   ├── __init__.py
│       │   ├── collector.py        # Schema 元数据采集 (asyncpg)
│       │   ├── cache.py            # Schema 内存缓存 & 检索
│       │   └── models.py           # Schema 数据模型 (Pydantic)
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── client.py           # OpenAI SDK 封装 (DeepSeek)
│       │   ├── prompts.py          # Prompt 模板管理
│       │   └── schema_retriever.py # Schema 检索增强 (关键词匹配)
│       ├── sql/
│       │   ├── __init__.py
│       │   ├── validator.py        # SQLGlot AST 安全校验
│       │   └── executor.py         # 只读事务执行 (asyncpg)
│       ├── verification/
│       │   ├── __init__.py
│       │   └── verifier.py         # 语义验证逻辑
│       ├── db/
│       │   ├── __init__.py
│       │   └── pool_manager.py     # 连接池管理 & 熔断
│       └── logging.py              # structlog 配置 & 脱敏处理器
└── tests/
    ├── conftest.py
    ├── test_config.py
    ├── test_validator.py
    ├── test_schema_cache.py
    ├── test_executor.py
    └── test_server.py
```

---

## 3. 配置模型

基于 `pydantic-settings`，从环境变量加载配置（对应 PRD §5）。

```python
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings

class DatabaseConfig(BaseSettings):
    """单个数据库的连接配置"""
    model_config = {"env_prefix": ""}  # 动态前缀

    host: str = "localhost"
    port: int = 5432
    database: str
    user: str
    password: SecretStr
    sslmode: str = "prefer"
    url: str | None = None  # 优先使用连接字符串

class LLMConfig(BaseSettings):
    model_config = {"env_prefix": "PG_MCP_LLM_"}

    api_key: SecretStr
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    max_tokens: int = 4096
    temperature: float = 0.0

class ServerConfig(BaseSettings):
    model_config = {"env_prefix": "PG_MCP_"}

    databases: str = ""  # 逗号分隔的数据库别名列表
    statement_timeout: str = "30s"
    lock_timeout: str = "5s"
    default_max_rows: int = 100
    max_field_size: int = 10240        # 10KB
    max_payload_size: int = 5242880    # 5MB
    pool_size_per_db: int = 5
    max_concurrent_queries: int = 20
    verify_mode: str = "off"           # off | metadata | sample
    verify_sample_rows: int = 5
    log_level: str = "INFO"
    access_token: SecretStr | None = None
    max_sql_length: int = 10000
    blocked_functions: list[str] = [...]  # 默认危险函数黑名单
    collect_view_definitions: bool = True
```

**数据库配置解析流程**：读取 `PG_MCP_DATABASES` 获取别名列表（如 `db1,db2`），再依次读取 `PG_MCP_DB1_*` / `PG_MCP_DB2_*` 系列环境变量，为每个别名构建 `DatabaseConfig` 实例。如果设置了 `PG_MCP_{ALIAS}_URL`，则优先使用连接字符串。

---

## 4. 核心数据模型

### 4.1 Schema 数据模型

```python
from pydantic import BaseModel

class ColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool
    is_primary_key: bool = False
    default: str | None = None
    comment: str | None = None

class ForeignKeyInfo(BaseModel):
    constraint_name: str
    source_column: str
    target_table: str
    target_column: str

class IndexInfo(BaseModel):
    name: str
    columns: list[str]
    index_type: str          # btree, hash, gin, gist...
    is_unique: bool

class TableInfo(BaseModel):
    schema_name: str
    table_name: str
    table_type: str          # "table" | "view"
    columns: list[ColumnInfo]
    foreign_keys: list[ForeignKeyInfo] = []
    indexes: list[IndexInfo] = []
    comment: str | None = None
    view_definition: str | None = None  # 仅视图
    row_estimate: int | None = None     # pg_class.reltuples

class EnumTypeInfo(BaseModel):
    schema_name: str
    type_name: str
    values: list[str]

class DatabaseSchema(BaseModel):
    database_name: str
    schemas: list[str]
    tables: list[TableInfo]
    enum_types: list[EnumTypeInfo] = []
    collected_at: str  # ISO 8601 时间戳
```

### 4.2 请求/响应模型

```python
from enum import Enum

class ReturnMode(str, Enum):
    SQL = "sql"
    RESULT = "result"

class VerifyMode(str, Enum):
    OFF = "off"
    METADATA = "metadata"
    SAMPLE = "sample"

class QueryRequest(BaseModel):
    question: str
    database: str | None = None
    return_mode: ReturnMode = ReturnMode.RESULT
    max_rows: int = 100
    verify_result: bool = False

class ColumnDef(BaseModel):
    name: str
    type: str

class QueryResult(BaseModel):
    columns: list[ColumnDef]
    rows: list[list]        # 每行是值列表
    returned_row_count: int
    truncated: bool
    total_row_count: int | None = None

class VerificationResult(BaseModel):
    match: str              # "yes" | "no" | "partial"
    explanation: str

class ErrorDetail(BaseModel):
    code: str
    message: str
    stage: str
    retryable: bool

class QueryResponse(BaseModel):
    sql: str | None = None
    database: str | None = None
    result: QueryResult | None = None
    verification: VerificationResult | None = None
    error: ErrorDetail | None = None
```

---

## 5. 模块详细设计

### 5.1 FastMCP 服务器 (`server.py`)

使用 FastMCP lifespan 管理连接池和 Schema 缓存的生命周期。

```python
from contextlib import asynccontextmanager
from fastmcp import FastMCP
from fastmcp.server.context import Context

@asynccontextmanager
async def lifespan(mcp: FastMCP):
    config = load_config()
    pool_manager = PoolManager(config)
    schema_cache = SchemaCache()
    llm_client = LLMClient(config.llm)

    await pool_manager.initialize()
    await schema_cache.warm_up(pool_manager)  # 采集摘要

    yield {
        "config": config,
        "pool_manager": pool_manager,
        "schema_cache": schema_cache,
        "llm_client": llm_client,
    }

    await pool_manager.close()

mcp = FastMCP(
    name="pg-mcp",
    description="Natural language PostgreSQL query server",
    lifespan=lifespan,
)

@mcp.tool(
    name="query",
    description="用自然语言查询 PostgreSQL 数据库，返回 SQL 或查询结果",
)
async def query_tool(
    question: str,
    database: str | None = None,
    return_mode: str = "result",
    max_rows: int = 100,
    verify_result: bool = False,
    ctx: Context = None,
) -> dict:
    """MCP tool 入口，编排完整的查询流水线"""
    deps = ctx.lifespan_context
    request = QueryRequest(
        question=question,
        database=database,
        return_mode=return_mode,
        max_rows=max_rows,
        verify_result=verify_result,
    )
    pipeline = QueryPipeline(deps, ctx)
    response = await pipeline.execute(request)
    return response.model_dump(exclude_none=True)
```

### 5.2 查询流水线 (`QueryPipeline`)

编排 PRD §6 中的完整处理流程，每个阶段记录日志与耗时。

```
QueryPipeline.execute(request)
  │
  ├─ 1. resolve_database(request)
  │     ├─ 有 database 参数 → 直接使用
  │     └─ 无 → _match_database_local() → 匹配失败 → _match_database_llm()
  │
  ├─ 2. ensure_schema_loaded(database)
  │     └─ schema_cache.get_or_load(database, pool_manager)  # 懒加载
  │
  ├─ 3. generate_sql(request, schema)
  │     ├─ schema_retriever.find_relevant_tables(question, schema)
  │     ├─ prompts.build_sql_generation_prompt(question, relevant_schema)
  │     └─ llm_client.chat(prompt) → 提取 SQL
  │
  ├─ 4. validate_sql(sql)
  │     └─ sql_validator.validate(sql) → 通过 / ValidationError
  │
  ├─ 5. [if return_mode == "sql"] → 返回 SQL
  │
  ├─ 6. execute_sql(database, sql, max_rows)
  │     └─ sql_executor.execute_readonly(pool, sql, max_rows)
  │
  ├─ 7. [if verify_result] verify_result(request, sql, result)
  │     ├─ 最多重试 2 次（重试时回到步骤 3 重新生成 SQL）
  │     └─ 重试的 SQL 同样经过步骤 4 校验
  │
  └─ 8. build_response() → QueryResponse
```

### 5.3 连接池管理 (`db/pool_manager.py`)

每个数据库维护一个独立的 asyncpg 连接池，支持熔断。

```python
import asyncpg
import asyncio
import time

class CircuitState:
    CLOSED = "closed"       # 正常：所有请求通过
    OPEN = "open"           # 熔断：拒绝所有请求
    HALF_OPEN = "half_open" # 试探：允许单个请求通过以检测恢复

class DatabasePool:
    """
    每数据库连接池 + 熔断器。

    状态转换:
      CLOSED ---[连续失败 >= threshold]--> OPEN
      OPEN   ---[等待 recovery_timeout]--> HALF_OPEN
      HALF_OPEN --[试探成功]--> CLOSED
      HALF_OPEN --[试探失败]--> OPEN（重置等待计时器）

    计入失败的错误类型:
      - 连接获取超时 (asyncio.TimeoutError)
      - 连接建立失败 (asyncpg.ConnectionError 等)
      - 数据库内部错误 (asyncpg.InternalServerError)
    不计入失败的错误类型:
      - SQL 语法/语义错误 (asyncpg.PostgresSyntaxError 等)
      - 查询超时 (asyncpg.QueryCanceledError) — 仅说明单条查询慢，不代表数据库不可用
    """

    CIRCUIT_TRIPPING_ERRORS = (
        asyncio.TimeoutError,
        asyncpg.InterfaceError,
        asyncpg.InternalServerError,
        ConnectionError,
        OSError,
    )

    def __init__(self, alias: str, db_config: DatabaseConfig, server_config: ServerConfig):
        self.alias = alias
        self.pool: asyncpg.Pool | None = None
        self.circuit_state = CircuitState.CLOSED
        self.failure_count = 0
        self.failure_threshold = 5       # 连续失败 N 次后熔断
        self.recovery_timeout = 60.0     # 熔断后等待 N 秒再试探
        self.last_failure_time = 0.0
        self._half_open_lock = asyncio.Lock()  # HALF_OPEN 时仅允许一个试探请求

    async def create_pool(self):
        dsn = self._build_dsn()
        self.pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=1,
            max_size=self.server_config.pool_size_per_db,
            max_inactive_connection_lifetime=300.0,
            command_timeout=60,
        )

    async def acquire(self) -> asyncpg.Connection:
        self._check_circuit()
        try:
            conn = await asyncio.wait_for(
                self.pool.acquire(),
                timeout=10.0,
            )
            self._on_success()
            return conn
        except self.CIRCUIT_TRIPPING_ERRORS:
            self._on_failure()
            raise
        except Exception:
            raise  # 非熔断类错误不影响计数

    def _check_circuit(self):
        if self.circuit_state == CircuitState.OPEN:
            if time.monotonic() - self.last_failure_time > self.recovery_timeout:
                self.circuit_state = CircuitState.HALF_OPEN
                logger.info("circuit_half_open", db=self.alias)
            else:
                raise CircuitOpenError(self.alias)
        if self.circuit_state == CircuitState.HALF_OPEN:
            if self._half_open_lock.locked():
                raise CircuitOpenError(self.alias)  # 已有试探请求进行中

    def _on_success(self):
        if self.circuit_state == CircuitState.HALF_OPEN:
            logger.info("circuit_recovered", db=self.alias)
        self.circuit_state = CircuitState.CLOSED
        self.failure_count = 0

    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.circuit_state == CircuitState.HALF_OPEN:
            self.circuit_state = CircuitState.OPEN
            logger.warning("circuit_open_again", db=self.alias)
        elif self.failure_count >= self.failure_threshold:
            self.circuit_state = CircuitState.OPEN
            logger.warning("circuit_opened", db=self.alias, failures=self.failure_count)

class PoolManager:
    def __init__(self, config: ServerConfig):
        self.pools: dict[str, DatabasePool] = {}
        self._semaphore = asyncio.Semaphore(config.max_concurrent_queries)

    async def initialize(self):
        """启动时为所有配置的数据库创建连接池"""
        for alias, db_config in self._parse_db_configs():
            try:
                pool = DatabasePool(alias, db_config, self.config)
                await pool.create_pool()
                self.pools[alias] = pool
            except Exception as e:
                logger.error("pool_create_failed", db=alias, error=str(e))

    async def execute_readonly(self, alias: str, sql: str, max_rows: int) -> ...:
        async with self._semaphore:
            db_pool = self.pools[alias]
            conn = await db_pool.acquire()
            try:
                async with conn.transaction(readonly=True):
                    await conn.execute(
                        f"SET LOCAL statement_timeout = '{self.config.statement_timeout}'"
                    )
                    await conn.execute(
                        f"SET LOCAL lock_timeout = '{self.config.lock_timeout}'"
                    )
                    rows = await conn.fetch(sql)
                    return rows
            finally:
                await db_pool.pool.release(conn)
```

**关键设计点:**
- `asyncpg.Connection.transaction(readonly=True)` 自动执行 `BEGIN READ ONLY`，满足 PRD FR-2.4-02
- `asyncio.Semaphore` 控制全局并发上限（FR-2.4-03）
- 熔断器通过失败计数 + 恢复超时实现（NFR-4.3-04）

### 5.4 Schema 采集与缓存 (`schema/`)

#### 5.4.1 采集器 (`collector.py`)

通过 `information_schema` 和 `pg_catalog` 查询元数据。

```python
class SchemaCollector:
    TABLES_QUERY = """
        SELECT t.table_schema, t.table_name, t.table_type
        FROM information_schema.tables t
        WHERE t.table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
        ORDER BY t.table_schema, t.table_name
    """

    COLUMNS_QUERY = """
        SELECT c.table_schema, c.table_name, c.column_name,
               c.data_type, c.is_nullable, c.column_default,
               pgd.description AS comment
        FROM information_schema.columns c
        LEFT JOIN pg_catalog.pg_statio_all_tables st
            ON c.table_schema = st.schemaname AND c.table_name = st.relname
        LEFT JOIN pg_catalog.pg_description pgd
            ON pgd.objoid = st.relid
            AND pgd.objsubid = c.ordinal_position
        WHERE c.table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
        ORDER BY c.table_schema, c.table_name, c.ordinal_position
    """

    FOREIGN_KEYS_QUERY = """
        SELECT tc.constraint_name, tc.table_schema, tc.table_name,
               kcu.column_name,
               ccu.table_schema AS target_schema,
               ccu.table_name AS target_table,
               ccu.column_name AS target_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')
    """

    # 类似的查询还有：INDEXES_QUERY, ENUM_TYPES_QUERY, VIEW_DEFINITIONS_QUERY...

    async def collect_full(self, conn: asyncpg.Connection) -> DatabaseSchema:
        """完整采集一个数据库的 schema 元数据"""
        tables_raw = await conn.fetch(self.TABLES_QUERY)
        columns_raw = await conn.fetch(self.COLUMNS_QUERY)
        fk_raw = await conn.fetch(self.FOREIGN_KEYS_QUERY)
        # ... 索引、枚举、视图定义等
        return self._assemble(tables_raw, columns_raw, fk_raw, ...)

    async def collect_summary(self, conn: asyncpg.Connection) -> dict:
        """仅采集摘要（启动时用）"""
        result = await conn.fetch("""
            SELECT table_schema, table_type, COUNT(*) as cnt
            FROM information_schema.tables
            WHERE table_schema NOT IN ('pg_catalog','information_schema','pg_toast')
            GROUP BY table_schema, table_type
        """)
        return {...}
```

#### 5.4.2 缓存 (`cache.py`)

```python
import asyncio
import time

class CacheEntry:
    def __init__(self, schema: DatabaseSchema, ttl: float = 3600.0):
        self.schema = schema
        self.loaded_at = time.monotonic()
        self.ttl = ttl

    @property
    def expired(self) -> bool:
        return (time.monotonic() - self.loaded_at) > self.ttl

class SchemaCache:
    def __init__(self, ttl: float = 3600.0, max_tables_per_db: int = 500):
        self._summaries: dict[str, dict] = {}        # alias → 摘要
        self._full: dict[str, CacheEntry] = {}        # alias → 完整 schema + TTL
        self._locks: dict[str, asyncio.Lock] = {}     # 防并发加载
        self._ttl = ttl
        self._max_tables = max_tables_per_db           # 单库表数上限，超出截断并警告

    async def warm_up(self, pool_manager: PoolManager):
        """启动时采集所有数据库的摘要"""
        for alias, db_pool in pool_manager.pools.items():
            try:
                conn = await db_pool.acquire()
                try:
                    self._summaries[alias] = await SchemaCollector().collect_summary(conn)
                finally:
                    await db_pool.pool.release(conn)
            except Exception as e:
                logger.warning("schema_summary_failed", db=alias)

    async def get_or_load(self, alias: str, pool_manager: PoolManager) -> DatabaseSchema:
        """懒加载 + TTL 过期自动刷新"""
        entry = self._full.get(alias)
        if entry and not entry.expired:
            return entry.schema

        lock = self._locks.setdefault(alias, asyncio.Lock())
        async with lock:
            entry = self._full.get(alias)
            if entry and not entry.expired:  # double-check
                return entry.schema
            schema = await self._load_full(alias, pool_manager)
            if len(schema.tables) > self._max_tables:
                logger.warning("schema_truncated", db=alias,
                               total=len(schema.tables), limit=self._max_tables)
                schema.tables = schema.tables[:self._max_tables]
            self._full[alias] = CacheEntry(schema, self._ttl)
            return schema

    async def refresh(self, alias: str | None, pool_manager: PoolManager):
        """强制刷新缓存（按库或全部）"""
        targets = [alias] if alias else list(self._full.keys())
        for a in targets:
            self._full.pop(a, None)
            await self.get_or_load(a, pool_manager)

    def list_databases(self) -> list[dict]:
        return [{"name": k, **v} for k, v in self._summaries.items()]
```

### 5.5 LLM 交互 (`llm/`)

#### 5.5.1 客户端 (`client.py`)

使用 OpenAI Python SDK 连接 DeepSeek（兼容 OpenAI API）。

```python
from openai import AsyncOpenAI

class LLMClient:
    def __init__(self, config: LLMConfig):
        self._client = AsyncOpenAI(
            api_key=config.api_key.get_secret_value(),
            base_url=config.base_url,
        )
        self._model = config.model
        self._max_tokens = config.max_tokens
        self._temperature = config.temperature

    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int | None = None,
    ) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=max_tokens or self._max_tokens,
            temperature=self._temperature,
        )
        return response.choices[0].message.content.strip()
```

#### 5.5.2 Prompt 模板 (`prompts.py`)

固定模板，系统指令 / 上下文 / 用户输入严格分层（FR-2.2.2-03）。

```python
SQL_GENERATION_SYSTEM = """You are a PostgreSQL SQL expert. Your task is to generate
a single read-only SQL query based on the user's question and the database schema
provided below.

Rules:
- Generate ONLY a single SELECT statement (CTEs with WITH are allowed).
- Do NOT use INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, or any DDL/DML.
- Do NOT use functions like pg_sleep, dblink, lo_export, set_config.
- Output ONLY the raw SQL statement, no markdown fences, no explanations.

Database schema:
{schema_context}
"""

SQL_GENERATION_USER = """Question: {question}"""

VERIFICATION_SYSTEM_METADATA = """You are a query result validator. Given a user's
question, the generated SQL, and result metadata, assess whether the query correctly
answers the question.

Respond in JSON: {{"match": "yes|no|partial", "explanation": "...", "suggested_sql": "..."}}
"""

DB_SELECTION_SYSTEM = """Given the user's question and the following database summaries,
select the most relevant database. Respond with ONLY the database alias name.

Databases:
{db_summaries}
"""
```

#### 5.5.3 Schema 检索增强 (`schema_retriever.py`)

基于关键词从 Schema 缓存中检索相关表子集（FR-2.2.2-02）。

```python
import re

class SchemaRetriever:
    def __init__(self, max_context_chars: int = 8000):
        self.max_context_chars = max_context_chars

    def find_relevant_tables(
        self, question: str, schema: DatabaseSchema
    ) -> list[TableInfo]:
        tokens = self._tokenize(question)
        scored: list[tuple[float, TableInfo]] = []
        for table in schema.tables:
            score = self._score_table(tokens, table)
            if score > 0:
                scored.append((score, table))
        scored.sort(key=lambda x: x[0], reverse=True)

        selected = []
        budget = self.max_context_chars
        for score, table in scored:
            rendered = self._render_table(table)
            if len(rendered) > budget:
                break
            selected.append(table)
            budget -= len(rendered)

        if not selected and schema.tables:
            selected = schema.tables[:10]

        return selected

    def _score_table(self, tokens: list[str], table: TableInfo) -> float:
        score = 0.0
        searchable = (
            table.table_name.lower()
            + " " + " ".join(c.name.lower() for c in table.columns)
            + " " + (table.comment or "").lower()
        )
        for token in tokens:
            if token in searchable:
                score += 1.0
            if token in table.table_name.lower():
                score += 2.0  # 表名匹配权重更高
        return score

    def render_schema_context(self, tables: list[TableInfo]) -> str:
        parts = []
        for t in tables:
            cols = ", ".join(
                f"{c.name} {c.type}{'(PK)' if c.is_primary_key else ''}"
                for c in t.columns
            )
            line = f"{t.schema_name}.{t.table_name} ({cols})"
            if t.comment:
                line += f"  -- {t.comment[:500]}"
            parts.append(line)

            for fk in t.foreign_keys:
                parts.append(
                    f"  FK: {fk.source_column} → {fk.target_table}.{fk.target_column}"
                )
        return "\n".join(parts)
```

### 5.6 SQL 安全校验 (`sql/validator.py`)

使用 SQLGlot 解析 SQL 为 AST，执行白名单 + 黑名单校验（FR-2.3）。

```python
import sqlglot
from sqlglot import exp

class ValidationError(Exception):
    def __init__(self, code: str, reason: str):
        self.code = code
        self.reason = reason

ALLOWED_ROOT_TYPES = (exp.Select, exp.Union, exp.Intersect, exp.Except)

BLOCKED_STATEMENT_TYPES = (
    exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop,
    exp.Alter, exp.Grant, exp.Set, exp.Command,
)

DEFAULT_BLOCKED_FUNCTIONS = {
    # 系统管理 / DoS
    "pg_sleep", "pg_terminate_backend", "pg_cancel_backend", "pg_reload_conf",
    "pg_rotate_logfile",
    # 文件 / 网络 I/O
    "pg_read_file", "pg_write_file", "pg_read_binary_file", "pg_stat_file",
    "lo_export", "lo_import", "lo_unlink", "lo_create",
    # Advisory locks（可阻塞其他会话）
    "pg_advisory_lock", "pg_advisory_lock_shared",
    "pg_try_advisory_lock", "pg_try_advisory_lock_shared",
    "pg_advisory_xact_lock", "pg_advisory_xact_lock_shared",
    # Replication / slot 操作
    "pg_create_logical_replication_slot", "pg_create_physical_replication_slot",
    "pg_drop_replication_slot", "pg_logical_slot_get_changes",
    "pg_logical_slot_peek_changes",
    # 配置 / session 操作
    "set_config", "pg_notify", "pg_listening_channels",
    # 扩展 / 外部访问
    "dblink", "dblink_exec", "dblink_connect", "dblink_disconnect",
    "dblink_send_query", "dblink_get_result",
    # 备份 / 恢复相关
    "pg_start_backup", "pg_stop_backup", "pg_switch_wal",
    "pg_create_restore_point",
}

class SQLValidator:
    def __init__(self, config: ServerConfig):
        self.max_length = config.max_sql_length
        self.blocked_functions = DEFAULT_BLOCKED_FUNCTIONS | set(config.blocked_functions)
        self.allow_explain_analyze = False

    def validate(self, sql: str) -> exp.Expression:
        if len(sql) > self.max_length:
            raise ValidationError("QUERY_TOO_LONG", f"SQL exceeds {self.max_length} chars")

        try:
            statements = sqlglot.parse(sql, dialect="postgres")
        except sqlglot.errors.ParseError as e:
            raise ValidationError("PARSE_ERROR", f"Invalid SQL syntax: {e}")

        # 单语句检查
        if len(statements) != 1:
            raise ValidationError(
                "MULTIPLE_STATEMENTS",
                f"Expected 1 statement, got {len(statements)}",
            )

        ast = statements[0]

        # EXPLAIN 处理
        if isinstance(ast, exp.Command) and ast.this == "EXPLAIN":
            self._check_explain(ast)
            return ast

        # 根节点白名单
        if not isinstance(ast, ALLOWED_ROOT_TYPES):
            raise ValidationError(
                "DISALLOWED_STATEMENT",
                f"Only SELECT statements are allowed, got {type(ast).__name__}",
            )

        # SELECT INTO 检查
        self._check_select_into(ast)

        # 遍历 AST 检查危险节点
        for node in ast.walk():
            # 黑名单语句类型
            if isinstance(node, BLOCKED_STATEMENT_TYPES):
                raise ValidationError(
                    "DISALLOWED_STATEMENT",
                    f"Statement type {type(node).__name__} is not allowed",
                )
            # 危险函数检查
            if isinstance(node, (exp.Anonymous, exp.Func)):
                func_name = (node.name or "").lower()
                if func_name in self.blocked_functions:
                    raise ValidationError(
                        "BLOCKED_FUNCTION",
                        f"Function '{func_name}' is not allowed",
                    )

        return ast

    def _check_select_into(self, ast: exp.Expression):
        for node in ast.walk():
            if isinstance(node, exp.Into):
                raise ValidationError(
                    "SELECT_INTO",
                    "SELECT INTO is not allowed",
                )

    def _check_explain(self, ast: exp.Expression):
        sql_text = ast.sql(dialect="postgres").upper()
        if "ANALYZE" in sql_text and not self.allow_explain_analyze:
            raise ValidationError(
                "EXPLAIN_ANALYZE",
                "EXPLAIN ANALYZE is not allowed by default",
            )
```

### 5.7 SQL 执行器 (`sql/executor.py`)

```python
import asyncpg
import json
import re

class SQLExecutor:
    def __init__(self, config: ServerConfig):
        self.config = config
        self._allowed_schemas = ["public"]  # 可配置的 search_path 白名单

    async def execute_readonly(
        self,
        pool: DatabasePool,
        sql: str,
        max_rows: int,
    ) -> QueryResult:
        conn = await pool.acquire()
        try:
            async with conn.transaction(readonly=True):
                await conn.execute(
                    f"SET LOCAL statement_timeout = '{self.config.statement_timeout}'"
                )
                await conn.execute(
                    f"SET LOCAL lock_timeout = '{self.config.lock_timeout}'"
                )
                # 限定 search_path，防止 LLM 生成的非限定名称解析到意外 schema
                schemas = ", ".join(self._allowed_schemas)
                await conn.execute(f"SET LOCAL search_path = {schemas}")

                # 使用 conn.prepare() 获取列元数据（即使零行也能返回列定义）
                prepared = await conn.prepare(sql)
                columns = [
                    ColumnDef(name=attr.name, type=attr.type.as_pg_type_name())
                    for attr in prepared.get_attributes()
                ]

                # 使用 cursor + fetch 限制行数，避免子查询包裹改变语义
                rows = await prepared.fetch(max_rows + 1)

                truncated = len(rows) > max_rows
                if truncated:
                    rows = rows[:max_rows]

                result_rows = [list(row.values()) for row in rows]
                result_rows = self._truncate_fields(result_rows)

                # 总 payload 大小检查
                payload = self._estimate_payload_size(result_rows)
                if payload > self.config.max_payload_size:
                    while result_rows and self._estimate_payload_size(result_rows) > self.config.max_payload_size:
                        result_rows.pop()
                    truncated = True

                return QueryResult(
                    columns=columns,
                    rows=result_rows,
                    returned_row_count=len(result_rows),
                    truncated=truncated,
                    total_row_count=None,
                )
        except asyncpg.QueryCanceledError:
            raise ExecutionError("EXECUTION_TIMEOUT", "Query timed out")
        except asyncpg.PostgresError as e:
            raise ExecutionError("EXECUTION_ERROR", self._sanitize_error(e))
        finally:
            await pool.pool.release(conn)

    def _truncate_fields(self, rows: list[list]) -> list[list]:
        """截断超大字段值（字符串、JSON、bytes 等）"""
        max_size = self.config.max_field_size
        for row in rows:
            for i, val in enumerate(row):
                if isinstance(val, str) and len(val) > max_size:
                    row[i] = val[:max_size] + "...[truncated]"
                elif isinstance(val, bytes) and len(val) > max_size:
                    row[i] = f"<binary {len(val)} bytes, truncated>"
                elif isinstance(val, (dict, list)):
                    serialized = json.dumps(val, default=str)
                    if len(serialized) > max_size:
                        row[i] = serialized[:max_size] + "...[truncated]"
        return rows

    def _estimate_payload_size(self, rows: list[list]) -> int:
        return sum(len(str(v)) for row in rows for v in row)

    def _sanitize_error(self, exc: asyncpg.PostgresError) -> str:
        """多层脱敏：移除可能暴露内部信息的 SQLSTATE 详情、hints、context"""
        msg = str(exc)
        msg = re.sub(r'(relation|table|column|function|schema|type) ".*?"',
                     r'\1 [redacted]', msg)
        msg = re.sub(r'DETAIL:.*', 'DETAIL: [redacted]', msg)
        msg = re.sub(r'HINT:.*', 'HINT: [redacted]', msg)
        msg = re.sub(r'CONTEXT:.*', 'CONTEXT: [redacted]', msg)
        msg = re.sub(r'LINE \d+:.*', '', msg)
        return msg.strip()
```

**关键改进（相比 v0.1）:**
- **search_path 锁定**: `SET LOCAL search_path` 防止非限定名称解析到意外 schema
- **conn.prepare()**: 即使零行结果也能返回准确的列元数据（而非从首行推断）
- **避免子查询包裹**: 使用 `prepared.fetch(N)` 替代 `SELECT * FROM (sql) LIMIT N`，不改变原 SQL 语义
- **多类型字段截断**: 除 `str` 外，还处理 `bytes`、`dict`（JSON）、`list`（数组）
- **payload 总量限制**: 循环裁剪行直到低于 `max_payload_size`
- **宽泛错误脱敏**: 不仅移除标识符名称，还清理 DETAIL/HINT/CONTEXT/LINE 信息

### 5.8 语义验证 (`verification/verifier.py`)

**verify_result (请求) 与 verify_mode (配置) 交互策略:**

| `config.verify_mode` | `request.verify_result` | 实际行为                        |
| -------------------- | ----------------------- | ------------------------------- |
| `off`                | `false`                 | 不验证                          |
| `off`                | `true`                  | 不验证（配置优先，拒绝客户端覆盖）|
| `metadata`           | `false`                 | 不验证（客户端未请求）          |
| `metadata`           | `true`                  | 元数据模式验证                  |
| `sample`             | `false`                 | 不验证（客户端未请求）          |
| `sample`             | `true`                  | 采样模式验证                    |

即：`verify_mode=off` 为硬开关（全局禁用，客户端无法覆盖）；`verify_mode=metadata|sample` 为能力声明，是否激活由客户端 `verify_result` 决定。

```python
class ResultVerifier:
    def __init__(self, config: ServerConfig, llm_client: LLMClient):
        self.config = config
        self.llm = llm_client

    def should_verify(self, request_verify: bool) -> bool:
        if self.config.verify_mode == "off":
            return False
        return request_verify

    async def verify(
        self, question: str, sql: str, result: QueryResult
    ) -> VerificationResult | None:
        mode = self.config.verify_mode
        if mode == "metadata":
            context = self._build_metadata_context(result)
        elif mode == "sample":
            context = self._build_sample_context(result)
        else:
            return None

        response = await self.llm.chat(
            system_prompt=VERIFICATION_SYSTEM_METADATA,
            user_message=f"Question: {question}\nSQL: {sql}\nResult info: {context}",
        )
        return self._parse_verification(response)

    def _build_metadata_context(self, result: QueryResult) -> str:
        cols = ", ".join(f"{c.name}({c.type})" for c in result.columns)
        return f"Columns: {cols}\nRow count: {result.returned_row_count}\nTruncated: {result.truncated}"

    def _build_sample_context(self, result: QueryResult) -> str:
        n = min(self.config.verify_sample_rows, len(result.rows))
        sample = result.rows[:n]
        cols = [c.name for c in result.columns]
        lines = [", ".join(cols)]
        for row in sample:
            lines.append(", ".join(str(v)[:100] for v in row))
        return "\n".join(lines)
```

### 5.9 日志与脱敏 (`logging.py`)

```python
import structlog
import hashlib

def sanitize_processor(logger, method_name, event_dict):
    """脱敏处理器：过滤敏感字段"""
    for key in ("password", "api_key", "token", "dsn"):
        if key in event_dict:
            event_dict[key] = "***REDACTED***"

    if "sql" in event_dict and event_dict.get("_log_level", "INFO") != "DEBUG":
        sql = event_dict["sql"]
        event_dict["sql_hash"] = hashlib.sha256(sql.encode()).hexdigest()[:16]
        del event_dict["sql"]

    for key in ("rows", "result_data", "prompt"):
        event_dict.pop(key, None)

    return event_dict

def configure_logging(level: str):
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            sanitize_processor,
            structlog.dev.ConsoleRenderer() if level == "DEBUG"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(structlog, level.upper(), structlog.INFO)
        ),
    )
```

---

## 6. 关键交互序列

### 6.1 正常查询流程（result 模式）

```
Client          FastMCP/Tool       Pipeline         LLM           Validator       Executor        PG
  │                │                 │               │               │               │             │
  │─ query(...) ──►│                 │               │               │               │             │
  │                │─ execute() ────►│               │               │               │             │
  │                │                 │─ resolve_db ──│               │               │             │
  │                │                 │─ load schema ─│───────────────│───────────────│── SQL ──────►│
  │                │                 │               │               │               │◄── rows ─────│
  │                │                 │─ retrieve ────│               │               │             │
  │                │                 │  relevant     │               │               │             │
  │                │                 │  schema       │               │               │             │
  │                │                 │─ gen prompt ──│               │               │             │
  │                │                 │─ chat() ─────►│               │               │             │
  │                │                 │◄── SQL ───────│               │               │             │
  │                │                 │─ validate() ──│───────────────│               │             │
  │                │                 │               │──► AST check ─│               │             │
  │                │                 │               │◄── OK ────────│               │             │
  │                │                 │─ execute() ───│───────────────│───────────────│             │
  │                │                 │               │               │─ BEGIN RO ────│────────────►│
  │                │                 │               │               │─ SET LOCAL ───│────────────►│
  │                │                 │               │               │─ SELECT... ───│────────────►│
  │                │                 │               │               │◄── rows ──────│◄────────────│
  │                │                 │               │               │─ COMMIT ──────│────────────►│
  │                │                 │◄── result ────│───────────────│───────────────│             │
  │◄── response ───│◄── response ────│               │               │               │             │
```

### 6.2 启动流程

```
1. 加载 ServerConfig（环境变量 → Pydantic）
2. 配置 structlog
3. FastMCP lifespan 开始：
   a. 创建 PoolManager
   b. 为每个数据库别名创建 asyncpg 连接池
      - 失败的数据库记录日志，不阻塞
   c. 创建 SchemaCache
   d. warm_up: 对每个已连接数据库采集 schema 摘要
   e. 创建 LLMClient
   f. yield 所有资源
4. FastMCP 开始接收请求（stdio / SSE）
```

---

## 7. 错误处理策略

所有内部异常被 `QueryPipeline` 统一捕获并映射为 `ErrorDetail`：

```python
EXCEPTION_MAP = {
    CircuitOpenError:    ("DB_CIRCUIT_OPEN", "Database temporarily unavailable", True),
    PoolAcquireTimeout:  ("DB_UNAVAILABLE",  "Could not connect to database", True),
    ValidationError:     ("VALIDATION_FAILED", None, False),  # message 取 reason
    ExecutionError:      (None, None, None),                   # 取自异常属性
    LLMError:            ("LLM_ERROR", "AI service unavailable", True),
    LLMParseError:       ("LLM_PARSE_ERROR", "Could not generate valid SQL", False),
    RateLimitError:      ("RATE_LIMITED", "Too many concurrent queries", True),
    AmbiguousDBError:    ("DB_AMBIGUOUS", None, False),
}

class QueryPipeline:
    async def execute(self, request: QueryRequest) -> QueryResponse:
        try:
            return await self._run(request)
        except tuple(EXCEPTION_MAP.keys()) as e:
            code, msg, retryable = EXCEPTION_MAP[type(e)]
            return QueryResponse(
                error=ErrorDetail(
                    code=code or e.code,
                    message=msg or e.message,
                    stage=self._current_stage,
                    retryable=retryable if retryable is not None else e.retryable,
                )
            )
```

---

## 8. 安全设计总结

| 防御层           | 机制                                             | 实现位置              |
| ---------------- | ------------------------------------------------ | --------------------- |
| Prompt 注入      | 固定模板 + 系统/用户分离                         | `llm/prompts.py`      |
| LLM 输出不可信   | 所有 SQL 经 AST 校验                             | `sql/validator.py`    |
| SQL 注入         | AST 白名单 + 单语句 + 扩展函数黑名单            | `sql/validator.py`    |
| 只读保障         | `transaction(readonly=True)` + AST 双重          | `sql/executor.py` + `validator.py` |
| Schema 隔离      | `SET LOCAL search_path` 限定白名单               | `sql/executor.py`     |
| DoS 防护         | SQL 长度限制 + statement_timeout + 并发限制 + advisory lock 黑名单 | 多处 |
| 数据泄露（LLM）  | 验证默认关闭 + 元数据模式 + 配置策略矩阵        | `verification/`       |
| 数据泄露（日志） | structlog 脱敏处理器 + SQL hash                  | `logging.py`          |
| 数据泄露（错误） | 多层错误脱敏（标识符+DETAIL+HINT+CONTEXT）       | `sql/executor.py`     |
| 数据泄露（结果） | payload 总量限制 + 多类型字段截断                | `sql/executor.py`     |
| 凭据保护         | Pydantic `SecretStr` + 环境变量                  | `config.py`           |
| 连接安全         | 默认 stdio + 可选 Bearer Token                   | `server.py`           |
| 可用性保护       | 完整熔断器（CLOSED→OPEN→HALF_OPEN 状态机）       | `db/pool_manager.py`  |

---

## 9. 依赖清单

```toml
# pyproject.toml [project.dependencies]
[project]
name = "pg-mcp"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastmcp>=2.0",
    "asyncpg>=0.29",
    "sqlglot>=26.0",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "openai>=1.0",
    "structlog>=24.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov",
    "ruff",
    "mypy",
]
```

---

## 10. 测试策略

| 层级       | 范围                                                    | 工具/方法                  |
| ---------- | ------------------------------------------------------- | -------------------------- |
| 单元测试   | `SQLValidator` — 白名单/黑名单/边界用例                 | pytest + sqlglot fixtures  |
| 单元测试   | `SchemaRetriever` — 关键词匹配、token 预算裁剪          | pytest                     |
| 单元测试   | Prompt 模板 — 模板渲染、长度控制                        | pytest                     |
| 单元测试   | `ServerConfig` — 环境变量解析、默认值                   | pytest + monkeypatch       |
| 集成测试   | `SchemaCollector` — 真实 PG 采集                        | pytest + Docker PG         |
| 集成测试   | `SQLExecutor` — 只读事务、超时、错误处理                | pytest + Docker PG         |
| 集成测试   | `QueryPipeline` — 端到端流水线（mock LLM）              | pytest-asyncio             |
| E2E 测试   | MCP 客户端 → FastMCP server → PG                        | FastMCP test client        |

**SQLValidator 测试用例矩阵（关键）:**

| 类别         | 输入示例                                         | 期望结果     |
| ------------ | ------------------------------------------------ | ------------ |
| 合法 SELECT  | `SELECT * FROM users`                            | 通过         |
| CTE          | `WITH t AS (SELECT 1) SELECT * FROM t`           | 通过         |
| UNION        | `SELECT 1 UNION SELECT 2`                        | 通过         |
| 多语句       | `SELECT 1; DROP TABLE x`                         | 拒绝         |
| INSERT       | `INSERT INTO t VALUES (1)`                       | 拒绝         |
| UPDATE       | `UPDATE t SET a=1`                               | 拒绝         |
| DELETE       | `DELETE FROM t`                                  | 拒绝         |
| CREATE       | `CREATE TABLE t (a int)`                         | 拒绝         |
| SELECT INTO  | `SELECT * INTO t FROM users`                     | 拒绝         |
| CTE + INSERT | `WITH t AS (SELECT 1) INSERT INTO x SELECT * FROM t` | 拒绝   |
| pg_sleep     | `SELECT pg_sleep(100)`                           | 拒绝         |
| dblink       | `SELECT * FROM dblink('...')`                    | 拒绝         |
| lo_export    | `SELECT lo_export(12345, '/tmp/x')`              | 拒绝         |
| EXPLAIN      | `EXPLAIN SELECT 1`                               | 通过（默认） |
| EXPLAIN ANALYZE | `EXPLAIN ANALYZE SELECT 1`                    | 拒绝（默认） |
| 超长 SQL     | 10001 字符的 SELECT                              | 拒绝         |
| COPY         | `COPY t TO '/tmp/x'`                            | 拒绝         |
| SET          | `SET statement_timeout = 0`                      | 拒绝         |
| Advisory lock | `SELECT pg_advisory_lock(1)`                    | 拒绝         |
| Notify       | `SELECT pg_notify('ch', 'msg')`                  | 拒绝         |
| Replication  | `SELECT pg_create_logical_replication_slot('s','p')` | 拒绝    |
| File read    | `SELECT pg_read_file('/etc/passwd')`             | 拒绝         |

---

## 11. 部署方式

### 11.1 本地 stdio 模式（默认）

```json
// Cursor MCP 配置示例
{
  "mcpServers": {
    "pg-mcp": {
      "command": "python",
      "args": ["-m", "pg_mcp"],
      "env": {
        "PG_MCP_DATABASES": "mydb",
        "PG_MCP_MYDB_URL": "postgresql://reader:pass@localhost:5432/mydb",
        "PG_MCP_LLM_API_KEY": "sk-...",
        "PG_MCP_LLM_BASE_URL": "https://api.deepseek.com",
        "PG_MCP_LLM_MODEL": "deepseek-chat"
      }
    }
  }
}
```

### 11.2 SSE 模式（远程）

```bash
PG_MCP_ACCESS_TOKEN=my-secret-token python -m pg_mcp --transport sse --port 8000
```

---

## 12. 需求追踪矩阵

| PRD 需求          | 设计模块                   | 实现要点                                   |
| ----------------- | -------------------------- | ------------------------------------------ |
| FR-2.1.1 Schema   | `schema/collector.py`      | information_schema + pg_catalog 查询        |
| FR-2.1.1-02 懒加载| `schema/cache.py`          | `get_or_load()` + asyncio.Lock             |
| FR-2.1.1-06 降级  | `schema/collector.py`      | try/except per query, log warning          |
| FR-2.2.2-02 检索  | `llm/schema_retriever.py`  | 关键词评分 + token 预算裁剪                |
| FR-2.2.2-03 Prompt| `llm/prompts.py`           | 固定模板 + 分层                            |
| FR-2.3 安全校验   | `sql/validator.py`         | SQLGlot AST + 白名单 + 函数黑名单         |
| FR-2.4-02 只读    | `sql/executor.py`          | `transaction(readonly=True)` + SET LOCAL   |
| FR-2.4-03 连接池  | `db/pool_manager.py`       | asyncpg.create_pool + Semaphore            |
| FR-2.5 语义验证   | `verification/verifier.py` | 元数据/采样双模式 + 默认关闭               |
| FR-2.6-04 错误    | `errors.py` + pipeline     | 统一 ErrorDetail 模型                      |
| NFR-4.1.1 访问控制| `server.py`                | stdio 默认 + 可选 Bearer Token             |
| NFR-4.3-04 熔断   | `db/pool_manager.py`       | CircuitState 状态机（完整 CLOSED→OPEN→HALF_OPEN） |
| NFR-4.4-03 日志   | `logging.py`               | structlog 脱敏处理器                       |

---

## 13. 待决事项（Open Questions）

以下问题在实现过程中需进一步确认：

| #  | 问题                                                                                             | 建议方向                                     |
| -- | ------------------------------------------------------------------------------------------------ | -------------------------------------------- |
| Q1 | `return_mode=result` 时列类型的精确契约？asyncpg 返回 Python 类型 vs 文本类型名，如何统一？      | 使用 `prepared.get_attributes()` 的 PG 类型名 |
| Q2 | 函数黑名单方式本质上是不完备的（扩展可引入任意函数）。是否需要走向函数白名单？                   | v1 维持黑名单 + 可配置扩展；标记为已知风险   |
| Q3 | EXPLAIN 是否为必需功能？如果允许，如何限制其资源消耗（大表的 EXPLAIN 可能很慢）？                | 默认禁止 EXPLAIN ANALYZE；纯 EXPLAIN 允许    |
| Q4 | 威胁模型假设：内部工具 vs 不可信用户？直接影响校验严格度和认证要求                               | v1 假设内部工具（stdio），远程部署需加固      |
| Q5 | 启动失败的数据库后续如何恢复？仅靠用户手动刷新？还是后台定时重试？                               | v1 手动刷新；v2 考虑后台探活                  |
| Q6 | Schema 检索使用字符预算而非 token 预算，大型 schema 可能超出 LLM 上下文窗口                      | v1 用字符近似（1 token ≈ 4 chars）；v2 考虑 tiktoken |
