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


## 构建 postgres 查询的 skill

在当前项目下创建一个新的 skill，要求：
1. 首先通过 psql (postgresql://postgres:123456@127.0.0.1:5432/) 探索这几个数据库：pg_mcp_small、pg_mcp_medium、pg_mcp_large，了解它们都有哪些 table/view/types/index 等等，每个数据库一个 md 文件，作为 skill 的 reference。
2. 用户可以给特定自然语言描述的查询的需求，skill 根据用户输入找到相应的数据库的 reference 文件，然后根据这些信息以及用户的输入来生成正确的 SQL。SQL只允许查询语句，不能有任何的写操作，不能有任何安全漏洞比如 SQL 注入，不能有任何危险的操作比如 sleep，不能有任何的敏感信息比如 API Key 等。
3. 使用 psql 测试这个 SQL 确保它能够执行并且返回有意义的结果。如果执行失败，则深度思考，重新生成 SQL，回到第 3 步。
4. 把用户的输入，生成的 SQL，以及返回的结果的一部分进行分析来确认结果是不是有意义，根据分析打个分数。10分非常 confident，0分非常不 confident。如果小于 7 分，则深度思考，重新生成 SQL，回到第 3 步。
5. 最后根据用户的输入是返回 SQL 还是返回 SQL 查询之后的结果（默认）来返回相应的内容
6. skill保存到当前项目 .claude/skills/pg-data 目录下


## simple agent 构建

基于 @specs/0010-simple-agent-design.md 的规范，使用 openai 构建一个 agent sdk，提供 agent 的核心功能，用户可以很方便地为 agent 添加自定义工具和 mcp。完成构建后，确保所有实现否符合 design spec，并提供几个 example 来展示如何使用（包含至少一个使用 mcp 的例子）。代码存放在 ./simple-agent 目录下

## system prompt

based on @specs/prompts/codex.txt and @specs/prompts/reviewer.txt think hard, we want to generate a system prompt for
./code-review-agent which is based on @simple-agent/. The codereview agent will only have read file / write file / git command tool so make sure system prompt don't mention unexisting stuff. And make sure system prompt focused on code review but have all the good parts of @specs/prompts/codex.txt. Write the prompts down to ./code-review-agent/prompts/system.md. Think ultra hard.


## 构建 codereview agent design spec

根据 @code-review-agent/system.md 文档，以及 @simple-agent/ 代码，构建一个 codereview agent。它包含这些工具：

- read file：读取当前目录下某个文件的内容
- write file：写入当前目录下某个文件的内容
- git command：执行 git 命令，尤其是可以根据用户的各种需求，找到合适的 git diff，包括不限于：branch diff, unstaged diff, staged diff, commit diff, pull request diff, 等等
- gh command：执行 gh 命令，尤其是可以根据用户的各种需求，找到合适的 gh 命令，包括不限于：pr view, pr diff, 等等

这些工具的使用方法，相关的例子要更新在 system.md 中，这样 LLM 可以很方便地使用这些工具。

用户可以这样使用 codereview agent：

- 帮我 review 当前 branch 新代码
- 帮我 review commit 之后的代码
- 帮我 review 最后 pull 的代码

仔细考虑这些需求，构建一个 solid 的设计文档，文档放在 ./specs/0011-code-review-agent-design.md 文件中。design doc 输出中文。


## 构建 code-review agent 代码

根据 @specs/0011-code-review-agent-design.md 文档，构建一个 code-review agent 的代码（使用 ./simple-agent 作为 dependency），代码放在 ./code-review-agent 目录下。代码要完整实现 design spec，符合其要求。实现完成后请根据几个场景运行测试，确保它正常工作。


## codex review

使用 codex review skill 对 ./code-review-agent 代码进行 review，确保代码符合 ./specs/0011-code-review-agent-design.md 的设计。将 rewiew 结果写在 ./specs/0012-code-review-agent-codex-review.md 文件中。