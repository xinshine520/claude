# PostgreSQL MCP Server

构建一个基于 Python 的 MCP (Model Context Protocol) 服务器，使 MCP 客户端（如 Cursor、Claude Desktop 等）能够通过自然语言描述来查询 PostgreSQL 数据库。服务器利用 OpenAI 大模型（gpt-5-mini）将自然语言转换为 SQL，并在执行前进行安全校验与结果验证，最终向用户返回生成的 SQL 语句或查询结果。
