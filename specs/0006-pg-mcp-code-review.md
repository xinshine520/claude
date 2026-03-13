# pg-mcp Code Review Report

| 字段         | 值                     |
| ------------ | ---------------------- |
| 文档编号     | REV-0006               |
| 关联设计     | DES-0002 v0.2          |
| 关联实现计划 | IMPL-0004              |
| 审查日期     | 2026-03-13             |
| 审查范围     | Phase 1–8 全部代码     |
| 审查工具     | 人工 + codex (gpt-5.2) |

---

## 1. Executive Summary

pg-mcp 代码整体质量较高，实现了设计文档 DES-0002 v0.2 中的主要功能，结构清晰，安全机制较完善。在 118 个非集成测试中全部通过，`ruff check` 零警告。

发现如下主要问题：

- **1 个 HIGH 级 Bug**：`PoolManager` 并发信号量在连接获取后立即释放，未覆盖查询执行期间，导致实际并发限制失效
- **1 个 HIGH 级 Bug**：`DatabasePool.release()` 未 `await` asyncpg 的协程方法，存在连接泄漏风险
- **3 个 MEDIUM 级问题**：SchemaCollector 异常静默吞噬未记录日志、executor 重复异常处理、search_path 仅允许 `public`
- **若干 LOW/INFO 项**：验证重试时 stage 未重置、DB 匹配本地算法 O(n²)、缺少 row_estimate 采集等

整体评定：**APPROVED_WITH_CHANGES**（High 级 Bug 需修复后方可用于生产）

---

## 2. Conformance Assessment

### 2.1 vs DES-0002（设计文档）

| 设计要求                          | 状态              | 说明                                                                                    |
| --------------------------------- | ----------------- | --------------------------------------------------------------------------------------- |
| FastMCP server + lifespan         | ✅ IMPLEMENTED    | `server.py` 正确实现 lifespan，yield deps，finally 关闭连接池                          |
| QueryPipeline 8 阶段              | ✅ IMPLEMENTED    | 全部 8 阶段按设计实现，`_current_stage` 追踪当前阶段                                   |
| Circuit breaker CLOSED/OPEN/HALF_OPEN | ✅ IMPLEMENTED | `pool_manager.py` 完整状态机，`_half_open_lock` 单试探设计正确                       |
| SchemaCollector 全部查询          | ✅ IMPLEMENTED    | TABLES/COLUMNS/FK/INDEXES/ENUMS/VIEWS/PK/TABLE_COMMENTS 全部实现，比设计更丰富        |
| SchemaCache TTL + 懒加载          | ✅ IMPLEMENTED    | TTL `CacheEntry.expired`、double-check lock、`asyncio.Lock` 防并发                     |
| SQLValidator AST 白名单+黑名单    | ✅ IMPLEMENTED    | 36 个黑名单函数（设计要求 30+），ALLOWED_ROOT_TYPES 覆盖 SELECT/UNION/INTERSECT/EXCEPT/WITH |
| LLMClient OpenAI SDK + DeepSeek   | ✅ IMPLEMENTED    | `AsyncOpenAI(base_url=...)` 正确配置，`extract_sql()` 支持 markdown 代码块             |
| ResultVerifier off/metadata/sample | ✅ IMPLEMENTED   | 策略矩阵完整，`_parse_verification()` JSON 解析带容错                                  |
| ErrorDetail code/stage/retryable  | ✅ IMPLEMENTED    | `EXCEPTION_MAP` 统一映射，stage 通过 `_current_stage` 传递                             |
| search_path 限制                  | ⚠️ PARTIAL       | 默认仅允许 `["public"]`，未暴露配置项供用户扩展多 schema 场景                          |
| payload 总量限制 + 字段截断       | ✅ IMPLEMENTED    | `_truncate_fields()` 处理 str/bytes/dict/list，`_estimate_payload_size()` 循环裁剪    |
| error sanitization                | ✅ IMPLEMENTED    | `_sanitize_error()` 正则替换 relation/table/column + 清除 DETAIL/HINT/CONTEXT/LINE     |
| SecretStr 凭据保护                | ✅ IMPLEMENTED    | `LLMConfig.api_key`、`DatabaseConfig.password`、`ServerConfig.access_token` 均为 SecretStr |
| 全局并发 Semaphore                | ⚠️ PARTIAL       | 信号量在 `acquire()` 后立即释放，未保护查询执行期间（见 HIGH-1）                       |
| Bearer Token 认证                 | ⚠️ PARTIAL       | 配置字段 `access_token` 存在，但 `server.py` 未实现 Token 校验逻辑                    |

### 2.2 vs IMPL-0004（实现计划）

| Phase | 名称                 | 状态              | 备注                                                      |
| ----- | -------------------- | ----------------- | --------------------------------------------------------- |
| 1     | 项目骨架与基础模块   | ✅ DONE           | 全部文件就绪，`pyproject.toml` 完整                       |
| 2     | SQL 安全校验器       | ✅ DONE           | 36 个黑名单函数（>30），32 个测试用例通过                 |
| 3     | 数据库连接池与执行器 | ⚠️ PARTIAL       | 功能完整，但信号量逻辑和 release 未 await 有缺陷（见 HIGH）|
| 4     | Schema 采集与缓存    | ✅ DONE           | 比设计更丰富（增加 PK 查询、TABLE_COMMENTS）               |
| 5     | LLM 交互层           | ✅ DONE           | 全部测试通过                                              |
| 6     | 语义验证层           | ✅ DONE           | 策略矩阵 6 种组合全部测试                                 |
| 7     | 服务器编排与入口     | ✅ DONE           | `server.py` + `__main__.py` 完整，支持 stdio/sse/http     |
| 8     | E2E 测试与文档       | ✅ DONE           | `README.md`、`.env.example`、`test_e2e.py` 就绪           |

---

## 3. Critical Issues

无。

---

## 4. High Severity Issues

### [HIGH-1] PoolManager.acquire() 信号量覆盖范围不足

**文件**: `pg-mcp/src/pg_mcp/db/pool_manager.py` 第 155–160 行  
**类别**: Bug  
**描述**：

```python
async def acquire(self, alias: str) -> asyncpg.Connection:
    async with self._semaphore:         # 信号量在此处获取
        ...
        return await self.pools[alias].acquire()  # acquire 返回后信号量立即释放！
```

`async with self._semaphore:` 块在 `acquire()` 返回时即结束，信号量在 **连接获取后、查询执行前** 就被释放。调用方在 `execute_with_connection()` 期间（可能数秒）不持有信号量，导致 `max_concurrent_queries=20` 的限制实际失效——可能同时存在远超 20 个并发执行中的查询。

**推荐修复**：

```python
# 方案 A：在 pipeline 层用 semaphore 包裹整个 acquire→execute→release 流程
async with self.pool_manager._semaphore:
    conn = await self.pool_manager.pools[alias].acquire_raw()
    try:
        result = await self.executor.execute_with_connection(conn, sql, max_rows)
    finally:
        self.pool_manager.pools[alias].release(conn)

# 方案 B：在 PoolManager 层暴露 async context manager
async with self.pool_manager.connection(alias) as conn:
    result = await self.executor.execute_with_connection(conn, sql, max_rows)
```

---

### [HIGH-2] DatabasePool.release() 未 await asyncpg 协程

**文件**: `pg-mcp/src/pg_mcp/db/pool_manager.py` 第 122–124 行  
**类别**: Bug  
**描述**：

```python
def release(self, conn: asyncpg.Connection) -> None:
    if self.pool:
        self.pool.release(conn)   # asyncpg.Pool.release() 是协程！未 await！
```

asyncpg `Pool.release()` 是异步方法。直接调用而不 await 只会创建一个协程对象并立即丢弃，**连接实际上未归还连接池**。持续操作后连接池将耗尽，所有后续查询挂起等待连接，表现为服务降级直至超时。

同样的问题出现在 `SchemaCache.warm_up()` (第 57 行)、`cache.py get_or_load()` (第 91 行) 中调用的 `db_pool.release(conn)`。

**推荐修复**：

```python
async def release(self, conn: asyncpg.Connection) -> None:
    if self.pool:
        await self.pool.release(conn)
```

并将所有调用方改为 `await db_pool.release(conn)`，或改用 `pool.release()` 的 `asynccontextmanager` 模式：`async with pool.acquire() as conn:`。

---

## 5. Medium Severity Issues

### [MED-1] SchemaCollector 异常静默吞噬，无日志

**文件**: `pg-mcp/src/pg_mcp/schema/collector.py` 第 127–158 行  
**类别**: Code-Quality  
**描述**：每个查询都有 `try/except Exception: pass`，权限不足或查询失败时完全静默，运维时难以诊断 schema 数据不完整的原因。设计文档 §5.4.1 明确要求"权限降级：try/except per query, **log warning**"，实现中缺少日志。  
**推荐修复**：改为 `except Exception as e: logger.warning("schema_query_failed", query="TABLES_QUERY", error=str(e))`

---

### [MED-2] executor.execute_readonly() 重复异常处理

**文件**: `pg-mcp/src/pg_mcp/sql/executor.py` 第 106–132 行  
**类别**: Code-Quality  
**描述**：`execute_readonly()` 先调用 `execute_with_connection()` —— 后者已处理 `asyncpg.QueryCanceledError` 和 `asyncpg.PostgresError` —— 之后又在外层重复 `except asyncpg.QueryCanceledError` 和 `except asyncpg.PostgresError`。这两个外层 except 实际上永远不会被触发（异常已被内层转换为 `ExecutionError`），属于死代码。  
**推荐修复**：删除 `execute_readonly()` 中重复的 try/except 块，仅保留 `finally: pool.release(conn)`。

---

### [MED-3] search_path 硬编码仅允许 public schema

**文件**: `pg-mcp/src/pg_mcp/sql/executor.py` 第 16 行  
**类别**: Missing-Feature  
**描述**：`DEFAULT_ALLOWED_SCHEMAS = ["public"]` 为硬编码，且 `ServerConfig` 未暴露配置项。使用多 schema 数据库（如 `pg_mcp_medium`、`pg_mcp_large` 有 `app`/`billing`/`catalog`/`finance` 等 schema）时，LLM 生成的非限定表名查询将失败，因为这些 schema 不在 search_path 中。

**推荐修复**：在 `ServerConfig` 中添加 `allowed_schemas: list[str] = ["public"]`，并在 `SQLExecutor` 构造时传入。

---

## 6. Low / Info Items

### [LOW-1] 验证重试时 _current_stage 未重置

**文件**: `server.py` 第 226–235 行  
**描述**：验证失败后重新执行 SQL 时，`_current_stage` 未更新为 `"execute_sql"`，如果重试阶段发生错误，ErrorDetail.stage 将显示 `"verify_result"` 而非 `"execute_sql"`，轻微误导排错。

---

### [LOW-2] _match_database_local() 内层循环 O(n×m)

**文件**: `server.py` 第 279–280 行  
**描述**：内层 `for tn in table_names: if t in tn.lower():` 每个 token 都遍历全部表名，table_names 可能有数百甚至数千条，对每个 question token 均为线性扫描。数据库表较多时性能较差。  
**建议**：将所有 table_names 预先合并为单一字符串或构建前缀索引再匹配。

---

### [LOW-3] row_estimate 未采集

**文件**: `schema/collector.py`  
**描述**：设计文档 §5.4.1 定义了 `ROW_ESTIMATES_QUERY`（从 `pg_class.reltuples` 获取估算行数），实现中未采集，`TableInfo.row_estimate` 恒为 `None`。行估算数据对 schema_retriever 评分及 LLM 上下文选择有辅助价值。

---

### [LOW-4] Bearer Token 认证逻辑未实现

**文件**: `server.py`  
**描述**：`ServerConfig.access_token` 字段存在，设计文档 §11.2 描述了远程 SSE 模式使用 Bearer Token 的方案，但 `server.py` 未实现 token 校验中间件。当前 SSE 模式无认证保护。  
**建议**：添加 FastMCP middleware 或在 lifespan 中注册认证中间件。

---

### [INFO-1] FastMCP exclude_args 已弃用

**文件**: `server.py` 第 112 行  
**描述**：`@mcp.tool(..., exclude_args=["ctx"])` 触发 FastMCP DeprecationWarning，建议改用 `Depends()` 依赖注入模式（FastMCP 2.14+）。

---

### [INFO-2] LLMClient 无调用超时设置

**文件**: `llm/client.py`  
**描述**：`AsyncOpenAI.chat.completions.create()` 调用未设置 `timeout` 参数，设计文档 §5 风险矩阵中提到"LLM 调用设超时（10s）"，当前实现依赖 httpx 默认超时（通常 600s），可能导致长时间阻塞。  
**建议**：在 `LLMConfig` 中增加 `timeout: float = 30.0`，并传入 `create()` 调用。

---

### [INFO-3] _sanitize_error() 覆盖 DETAIL/HINT 仅第一次出现

**文件**: `executor.py` 第 162–164 行  
**描述**：`re.sub(r"DETAIL:.*", "DETAIL: [redacted]", msg)` 使用 `.*`（非贪婪 dotall），仅替换每行第一次 DETAIL。若错误消息跨行或包含多个 DETAIL 段落，可能部分未脱敏。  
**建议**：加 `re.DOTALL` 标志或使用 `re.MULTILINE | re.DOTALL`。

---

## 7. Security Review

### 7.1 SQL 注入防护

| 检查点                              | 结果   | 说明                                                                                  |
| ----------------------------------- | ------ | ------------------------------------------------------------------------------------- |
| 黑名单函数数量                      | ✅ 充足 | 36 个函数，覆盖 DoS/文件I/O/advisory lock/replication/外部访问/备份                  |
| AST 白名单根节点                    | ✅     | `Select/Union/Intersect/Except/With` 均允许，其他类型拒绝                             |
| 嵌套危险语句检测                    | ✅     | `root.walk()` 遍历全树，包括 CTE body                                                 |
| SELECT INTO 检测                    | ✅     | 单独 `_check_select_into()` walk 全树                                                 |
| schema 限定函数绕过（如 `pg_catalog.pg_sleep`）| ✅ | `_get_func_name()` 提取 basename，可绕过 schema 限定                         |
| 多语句注入（`; DROP TABLE`）        | ✅     | `len(statements) != 1` 校验                                                           |
| 单次 SQL 长度限制                   | ✅     | `max_sql_length=10000`，在 strip 之前检查                                             |

**已知局限**（设计文档 Q2 已标注）：函数黑名单本质上不完备，用户自定义扩展函数无法被拦截。v1 通过可配置 `blocked_functions` 缓解。

### 7.2 只读保障

- ✅ `conn.transaction(readonly=True)` → asyncpg 执行 `BEGIN READ ONLY`，PG 层拒绝写操作
- ✅ `SET LOCAL statement_timeout` + `SET LOCAL lock_timeout` 防止长时阻塞
- ⚠️ `SET LOCAL search_path` 默认仅含 `public`（见 MED-3）

### 7.3 凭据保护

- ✅ `LLMConfig.api_key: SecretStr` — `.get_secret_value()` 仅在必要时调用
- ✅ `DatabaseConfig.password: SecretStr` — DSN 构建时提取
- ✅ `ServerConfig.access_token: SecretStr | None` — 字段存在
- ✅ structlog `sanitize_processor` 过滤 `password`/`api_key`/`token`/`dsn` 字段

### 7.4 错误信息脱敏

- ✅ `_sanitize_error()` 替换 `relation/table/column/function/schema/type "xxx"` 为 `[redacted]`
- ✅ 清除 DETAIL/HINT/CONTEXT/LINE 信息
- ⚠️ 正则未使用 `re.DOTALL`，多行消息可能部分泄露（见 INFO-3）

### 7.5 数据量限制

- ✅ `max_field_size=10240`（10KB）：str/bytes/dict/list 均截断
- ✅ `max_payload_size=5242880`（5MB）：循环 `pop()` 裁剪直至达标
- ✅ `max_rows + 1` fetch 再截断，正确判断 `truncated=True`

---

## 8. Test Coverage Analysis

| 测试文件                   | 覆盖内容                                  | 通过  | 缺口                                          |
| -------------------------- | ----------------------------------------- | ----- | --------------------------------------------- |
| `test_validator.py`        | 32 个用例，覆盖全部 22 个设计矩阵场景     | ✅    | 无重大缺口                                    |
| `test_circuit.py`          | 8 个用例，熔断器状态机完整验证            | ✅    | 未测试半开状态下并发试探竞争                  |
| `test_verifier.py`         | 18 个用例，策略矩阵 6 种组合 + JSON 容错  | ✅    | 未测试 verify+retry 完整流程（仅单元）        |
| `test_pipeline.py`         | 6 个用例，result/sql 模式、DB 推断、错误  | ✅    | 缺少：验证重试逻辑、并发限制触发、payload 截断 |
| `test_schema_cache.py`     | TTL、懒加载、并发锁、截断警告             | ✅    | 缺少：get_or_load 对不存在 alias 的处理       |
| `test_schema_retriever.py` | 关键词匹配、预算裁剪、fallback            | ✅    | 无重大缺口                                    |
| `test_server.py`           | tool 注册、lifespan 启动/关闭             | ✅    | E2E lifespan 因 DB 不可用跳过                 |
| `test_e2e.py`              | 5 个 E2E 场景（Docker PG + mock LLM）     | ⏸️   | Docker PG 未运行时跳过                        |
| `test_executor.py`         | 集成测试（executor + 真实 PG）            | ⏸️   | 标记为 integration，需 Docker PG              |

**关键缺失测试**：
1. `test_pipeline.py` 缺少验证重试（`suggested_sql` 路径）的端到端测试
2. 信号量并发限制实际效果未覆盖
3. `release()` 未 await 引起的连接池耗尽场景无测试

---

## 9. Recommendations

### P0（上线前必须修复）

1. **[HIGH-2] 修复 `pool.release()` 未 await**：在 `DatabasePool.release()`、`SchemaCache.warm_up()`、`cache.get_or_load()` 中加 `await`，或改用 `async with pool.acquire() as conn:` 的 context manager 模式。

2. **[HIGH-1] 修复信号量覆盖范围**：将 `_semaphore` 的持有范围延伸到整个查询执行期间。最简实现：将 `server.py` 中的 acquire/execute/release 三步包裹在 `async with self.pool_manager._semaphore:` 中，`PoolManager.acquire()` 不再内部使用信号量。

### P1（近期优化）

3. **[MED-1] SchemaCollector 异常加日志**：每个 try/except 加 `logger.warning()` 便于运维诊断。

4. **[MED-3] search_path 支持多 schema 配置**：在 `ServerConfig` 增加 `allowed_schemas: list[str]` 并传入 `SQLExecutor`。

5. **[INFO-2] LLMClient 添加调用超时**：设置 `timeout=30.0`，防止 LLM 调用长时阻塞服务。

### P2（中期改进）

6. **[LOW-4] 实现 Bearer Token 认证**：SSE/HTTP 模式下对 `access_token` 进行校验。

7. **[LOW-3] 采集 row_estimate**：增加 `ROW_ESTIMATES_QUERY` 提升 schema_retriever 评分质量。

8. **[INFO-1] 迁移 FastMCP exclude_args**：使用 `Depends()` 替换已弃用参数。

9. **[INFO-3] 修复 _sanitize_error 正则**：增加 `re.DOTALL` 标志，确保多行消息完整脱敏。

---

## 10. Verdict

**APPROVED_WITH_CHANGES**

pg-mcp 代码结构清晰，安全设计完善，功能基本符合 DES-0002 和 IMPL-0004 的要求。但存在两个 HIGH 级 Bug：

1. `pool.release()` 未 await 会导致长时运行后连接池耗尽，属于**生产级缺陷**
2. 并发信号量覆盖范围不足，`max_concurrent_queries` 限制实际未生效

这两个问题在高并发场景下会导致服务不稳定，**必须在部署到生产前修复**。修复后可正式发布。
