# 项目说明

## 构建 mcp server

主要的需求是在Python下面创建一个Postgres的mcp：用户可以给特定自然语言描述的查询的需求，然后mcp server 根据结果来返回一个SQL或者返回这个查询的结果。mcp的服务器在启动的时候，应该读取它都有哪些可以访问的数据库，并且缓存这些数据库的schema：了解每一个数据库下面都有哪些 table/view/types/index 等等，然后根据这些信息以及用户的输入去调用OpenAI的大模型（gpt-5-mini）来生成 SQL。之后mcp server应该来校验这个sql只允许查询的语句然后测试这个sql确保它能够执行并且返回有意义的结果：这里也可以把用户的输入生成的sql以及返回的结果的一部分调用openai来确认这样可以确保它的结果是不是有意义。最后根据用户的输入是返回SQL还是返回SQL查询之后的结果来返回相应的内容根据这些需求帮我构建一个详细的需求文档，先不要著急去做设计，等我review完这个需求文档之后呢我们再来讨论设计，文档放在 ./specs/0001-pg-mcp-prd.md 文件中。


## commit/review

目前只需要 query 即可，其它意义不大；另外调用 /codex-code-review 让 codex review 这个需求文档，并更新


## 构建 pg-mcp 的设计文档

根据 @specs/0001-pg-mcp-prd.md 文档，使用 FastMCP、Asyncpg、SQLGlot、Pydantic以及deepseek(openai) 构建 pg-mcp 的设计文档，文档放在 ./specs/0002-pg-mcp-design.md


## codex review design document

使用 sub agent 调用 /codex-code-review  让 codex review @specs/0002-pg-mcp-design.md 文件。之后仔细阅读 review 的结果，思考是否合理，然后相应地更新 @specs/0002-pg-mcp-design.md 文件。


## impl plan

根据 @specs/0002-pg-mcp-design.md 文档，构建 pg-mcp 的实现计划，think ultra hard，文档放在 @specs/0004-pg-mcp-impl-plan.md 文件中。之后调用 /codex-code-review 让 codex review @specs/0004-pg-mcp-impl-plan.md 文件，并构建 ./specs/0005-pg-mcp-impl-plan-review.md 文件。


## 实现 pg-mcp

根据 @specs/0004-pg-mcp-impl-plan.md 和 @specs/0002-pg-mcp-design.md 文档，使用 sub agent 完整实现 pg-mcp phase 1-5。代码放在 ./pg-mcp 目录下。

根据 @specs/0004-pg-mcp-impl-plan.md 和 @specs/0002-pg-mcp-design.md 文档，使用 sub agent 完整实现 pg-mcp phase 6到剩下所有。代码放在 ./pg-mcp 目录下。

根据 @specs/0004-pg-mcp-impl-plan.md 文档，使用 sub agent 完整实现 pg-mcp phase 9-11。代码放在 ./pg-mcp 目录下。

使用 sub agent调用 /codex-code-review  让 codex review 整个代码，看其是否符合 @specs/0002-pg-mcp-design.md 和 @specs/0004-pg-mcp-impl-plan.md 。把 review 结果写到 ./specs/0006-pg-mcp-code-review.md 文件。

根据 @specs/0006-pg-mcp-code-review.md 文档，使用 sub agent 修复 pg-mcp 整个代码，并将修复结果写到 ./specs/0009-pg-mcp-code-review-result.md 文件。


## pg-mcp test plan

根据 @specs/0004-pg-mcp-impl-plan.md 和 @specs/0002-pg-mcp-design.md 文档，构建 pg-mcp 的测试计划，think ultra hard，文档放在 /specs/0007-pg-mcp-test-plan.md 文件中。之后调用 /codex-code-review  让 codex review  /specs/0007-pg-mcp-test-plan.md 文件，并构建 /specs/0008-pg-mcp-test-plan-review.md 文件。

## pg-cmp 测试数据库

根据 @specs/0001-pg-mcp-prd.md 在 ./pg-mcp/fixtures 下构建三个有意义的数据库，分别有少量，中等量级，以及大量的 table/view/types/index 等schema，且有足够多的数据。生成这三个数据库的 sql 文件，并构建 PowerShell 脚本 来重建这些测试数据库。


## 构建 pg-mcp 的测试用例

根据这些 @pg-mcp/fixtures ，假设用户要用自然语言提问，然后 pg-mcp来生成相应的 sqL，帮我生成一个test.md的文档，里面包含各种对数据库内部数据的简单到复杂的提问

对于 @w5/pg-mcp，将这个 mcp 添加到 claude code 中，打开一个 claude code headless cli 选择 @w5/pg-mcp/fixtures/TEST_QUERIES.md 下面的某些 query，运行，查看是否调用这个 mcp，结果是否符合预期

直接用本地的 `uvx --refresh --from pg-mcp pg-mcp` 来运行 mcp server


## 增加需求（已同步至 specs/0004-pg-mcp-impl-plan.md Phase 9-11）

1.多数据库与安全控制​功能虽在设计中有承诺，但实际未能启用：服务器始终使用单一执行器，无法强制实施表 / 列访问限制或 EXPLAIN 策略，这可能导致请求访问错误数据库，且敏感对象无法得到保护。→ **Phase 9**

2.弹性与可观测性模块（如速率限制、重试 / 退避机制、指标 / 追踪系统）仅停留在设计层面，尚未整合到实际请求处理流程中。→ **Phase 10**

3.响应 / 模型缺陷（重复的 to_dict 方法、未使用的配置字段）及测试覆盖不足，导致当前系统行为偏离实施方案，且难以进行有效验证。→ **Phase 11**