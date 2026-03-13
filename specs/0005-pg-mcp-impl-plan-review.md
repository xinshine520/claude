# REVIEW-0005: IMPL-0004 实现计划 Review 报告

| 字段       | 值                          |
| ---------- | --------------------------- |
| 文档编号   | REVIEW-0005                 |
| 评审对象   | IMPL-0004 v0.1              |
| 评审工具   | Codex CLI (gpt-5.2)         |
| 评审日期   | 2026-03-12                  |

---

## 1. 总体评价

- 分 Phase 自底向上构建，每阶段带验证与测试验收标准，结构清晰
- SQL 安全校验（Phase 2）前置是正确的安全取向
- 依赖图与"无 mock 不上层"的测试策略，能显著降低集成阶段返工
- 测试分层（单元/集成/E2E）规划合理

---

## 2. 发现清单

### F1: 实现原则与 Phase 编号不一致

| 属性     | 值                                                                 |
| -------- | ------------------------------------------------------------------ |
| 位置     | §1 实现原则 第 4 条                                                |
| 严重度   | **Medium**                                                         |
| 描述     | 原文："Phase 5 结束即可启动一个功能最小但完整的 MCP server"，但实际 server/lifespan/tool 编排在 Phase 7。Phase 5 仅完成 LLM 交互层，距可运行 server 还差验证层和编排层。 |
| 建议     | 改为"Phase 7 结束即可启动功能完整的 MCP server"，或在 Phase 5 末尾增加一个可选的最小 server 骨架验证步骤。 |

---

### F2: Phase 3 缺少对 Phase 2 的显式前置依赖

| 属性     | 值                                                                 |
| -------- | ------------------------------------------------------------------ |
| 位置     | §3 Phase 3 前置依赖                                                |
| 严重度   | **Medium**                                                         |
| 描述     | Phase 3（执行器/连接池）前置依赖只写了 Phase 1，但依赖图显示 Phase 2（validator）影响执行层。从安全角度应明确"执行前必须经过 validator"。 |
| 建议     | Phase 3 前置依赖增加 Phase 2；在验收标准中补充"集成测试需验证 validator → executor 调用链路"。 |

---

### F3: SQLGlot CTE (WITH) 解析的白名单策略不明确

| 属性     | 值                                                                 |
| -------- | ------------------------------------------------------------------ |
| 位置     | §3 Phase 2 关键实现细节                                            |
| 严重度   | **High**                                                           |
| 描述     | PostgreSQL 的 `WITH ... SELECT` 在 SQLGlot 中通常表现为 `exp.With` 包裹在 `Select` 外部。仅白名单 `Select/Union/Intersect/Except` 可能误杀合法 CTE 查询，或需要额外处理 `WITH` 挂载场景。 |
| 建议     | 在 Phase 2 实现细节中补充：1) 需在测试中验证 SQLGlot 对 `WITH...SELECT` 的实际 AST 结构；2) 如果根节点是 `exp.With`，需检查其最终主体（body）是否为允许的只读查询类型；3) 补充测试用例 `WITH t AS (SELECT 1) SELECT * FROM t` 的 AST 结构分析。 |

---

### F4: EXPLAIN 校验规则不够全面

| 属性     | 值                                                                 |
| -------- | ------------------------------------------------------------------ |
| 位置     | §3 Phase 2 SQLValidator                                            |
| 严重度   | **Medium**                                                         |
| 描述     | 当前仅处理 `EXPLAIN ANALYZE`，但 PostgreSQL 支持多种 EXPLAIN 选项变体：`EXPLAIN (ANALYZE, BUFFERS, TIMING)` / `EXPLAIN (ANALYZE true)` 等。此外 EXPLAIN 可作为前缀包裹任意语句（含 DML），需要验证被 EXPLAIN 包裹的语句本身是否合法。 |
| 建议     | 补充：1) 解析 EXPLAIN 选项中的 ANALYZE / BUFFERS / TIMING 等关键字；2) 对 EXPLAIN 包裹的内部语句递归执行白名单校验；3) 在测试矩阵中增加 `EXPLAIN (ANALYZE) SELECT 1`、`EXPLAIN DELETE FROM t` 等用例。 |

---

### F5: 危险函数黑名单缺少 schema 限定名匹配策略

| 属性     | 值                                                                 |
| -------- | ------------------------------------------------------------------ |
| 位置     | §3 Phase 2 关键实现细节                                            |
| 严重度   | **High**                                                           |
| 描述     | 当前仅描述"函数名统一小写比较"，但攻击者可使用 schema 限定调用绕过：`pg_catalog.pg_sleep(100)` 或 `public.pg_sleep(100)`。此外缺少对 `pg_ls_dir`、`COPY ... PROGRAM` 等数据外带向量的说明。 |
| 建议     | 1) 明确函数名匹配逻辑：对 schema-qualified 函数名，提取最终函数名部分进行匹配；2) 补充 `pg_ls_dir`、`pg_stat_file` 到黑名单；3) 在测试矩阵增加 `SELECT pg_catalog.pg_sleep(1)` 用例；4) 明确 `COPY` 语句（AST 类型 `Copy`）也应加入黑名单语句类型。 |

---

### F6: 只读执行安全增强措施不完整

| 属性     | 值                                                                 |
| -------- | ------------------------------------------------------------------ |
| 位置     | §3 Phase 3 SQLExecutor                                             |
| 严重度   | **Medium**                                                         |
| 描述     | 仅依赖 `transaction(readonly=True)` 可能不够"抗误配"。设计文档中已有 `SET LOCAL statement_timeout` 和 `SET LOCAL lock_timeout`，但实现计划未提及 `SET LOCAL idle_in_transaction_session_timeout` 防止长连接占用，也未要求在测试中验证"PG 侧拒绝写操作"而非应用层字符串判断。 |
| 建议     | 1) 补充 `SET LOCAL idle_in_transaction_session_timeout`；2) 在 Phase 3 集成测试中明确要求一个"尝试写操作被 PG 拒绝"的用例（而非应用层 mock）；3) 考虑是否需要 `SET LOCAL default_transaction_read_only = on` 双重保障。 |

---

### F7: LLM 响应解析策略过于脆弱

| 属性     | 值                                                                 |
| -------- | ------------------------------------------------------------------ |
| 位置     | §3 Phase 5 LLM 响应解析实现要点                                    |
| 严重度   | **Medium**                                                         |
| 描述     | 当前策略为"正则匹配 markdown 代码块或取整个响应"，这在实际中非常脆弱。LLM 经常会附带解释文字、多个代码块、或不一致的格式。 |
| 建议     | 1) 考虑使用 JSON 结构化输出（DeepSeek 支持）：`{"sql": "...", "reasoning": "..."}`，在 system prompt 中强制要求 JSON 格式；2) 如仍用自由文本，定义多层解析策略：a) 正则匹配 ```sql 块 → b) 正则匹配任意 ``` 块 → c) 去除非 SQL 行 → d) 全文作为 SQL；3) 在 Phase 5 测试中增加"LLM 返回混合文字+代码"的解析容错用例。 |

---

### F8: Schema 上下文裁剪优先级缺失

| 属性     | 值                                                                 |
| -------- | ------------------------------------------------------------------ |
| 位置     | §3 Phase 5 SchemaRetriever                                         |
| 严重度   | **Low**                                                            |
| 描述     | 计划提到"8000 chars ≈ 2000 tokens"的字符预算，但未定义当预算不足时，Schema 元素的裁剪优先级顺序（表名 > 列 > 注释 > 外键 > 索引 > 视图定义）。不同实现者可能做出不一致的选择。 |
| 建议     | 在 Phase 5 的 `SchemaRetriever` 实现要点中增加"裁剪优先级"定义：1) 表名+列名+列类型（最小集合，不可省略）；2) 主键/外键关系；3) 表/列注释；4) 索引信息；5) 视图定义（最先裁剪）。 |

---

### F9: 验证重试路径缺少专用集成测试

| 属性     | 值                                                                 |
| -------- | ------------------------------------------------------------------ |
| 位置     | §3 Phase 7 验证重试逻辑                                            |
| 严重度   | **Medium**                                                         |
| 描述     | 重试逻辑在伪代码中提到"重试的 SQL 也必须过校验"，但测试计划中未明确要求一个覆盖完整重试路径（LLM 建议新 SQL → validator → executor → 结果限制）的集成测试用例。 |
| 建议     | 在 Phase 7 `test_pipeline.py` 中增加专项测试：1) mock LLM 首次返回不佳结果 → 验证器标记 `match=no` 并建议新 SQL → 重试成功；2) mock LLM 建议的新 SQL 不通过 validator → 重试被拒，返回原结果；3) 重试次数达到上限 → 返回最后一次结果。 |

---

## 3. 发现统计

| 严重度   | 数量 | 编号              |
| -------- | ---- | ----------------- |
| Critical | 0    | —                 |
| High     | 2    | F3, F5            |
| Medium   | 5    | F1, F2, F4, F6, F9|
| Low      | 1    | F8                |
| Info     | 1    | —（总体评价）     |

---

## 4. 建议处理优先级

### 必须修复（High + 关键 Medium）

| 优先级 | 编号 | 动作                                                        |
| ------ | ---- | ----------------------------------------------------------- |
| P0     | F3   | Phase 2 补充 CTE/WITH AST 处理策略及测试用例                |
| P0     | F5   | Phase 2 补充 schema-qualified 函数匹配 + `pg_ls_dir`/`COPY` |
| P1     | F1   | 修正实现原则中 Phase 编号                                    |
| P1     | F2   | Phase 3 前置依赖增加 Phase 2                                 |
| P1     | F4   | Phase 2 补充 EXPLAIN 选项变体校验及内部语句递归检查          |
| P1     | F6   | Phase 3 补充 `idle_in_transaction_session_timeout` + PG 侧写拒绝测试 |
| P1     | F9   | Phase 7 补充验证重试路径专用集成测试                         |

### 建议改进（Low/Info）

| 优先级 | 编号 | 动作                                                        |
| ------ | ---- | ----------------------------------------------------------- |
| P2     | F7   | Phase 5 增强 LLM 响应解析策略，考虑 JSON 结构化输出         |
| P2     | F8   | Phase 5 定义 Schema 裁剪优先级                               |

---

## 5. 未覆盖项（补充发现）

以下是评审过程中额外识别的、实现计划中未充分涉及的事项：

| #  | 事项                                                                  | 建议                                          |
| -- | --------------------------------------------------------------------- | --------------------------------------------- |
| S1 | CI/CD 集成未提及                                                      | 补充 GitHub Actions / CI 配置 Phase（或纳入 Phase 8） |
| S2 | `ruff` / `mypy` 在每个 Phase 末尾的运行时机未明确                     | 建议每个 Phase 验收标准统一要求 lint + type check |
| S3 | 未提及 `conftest.py` 的创建时机                                       | 建议在 Phase 1 或 Phase 3（首个需要 fixtures 的阶段）创建 |
| S4 | 多数据库配置解析（`PG_MCP_DATABASES` → 各别名）逻辑复杂度被低估       | Phase 1 应增加多数据库解析的详细测试用例       |
| S5 | 未提及代码格式化工具配置（ruff format / pyproject.toml [tool.ruff]）  | 建议在 Phase 1 的 pyproject.toml 中包含 ruff 配置 |
