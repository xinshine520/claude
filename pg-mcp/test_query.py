"""Test pg-mcp with actual query."""
import asyncio
import os

# Set environment variables
os.environ['PG_MCP_DATABASES'] = 'pg_mcp_test'
os.environ['PG_MCP_PG_MCP_TEST_URL'] = 'postgresql://postgres:123456@127.0.0.1:5432/pg_mcp_test'
os.environ['PG_MCP_LLM_API_KEY'] = 'sk-eb62d7185a224320b44fc2929928dcac'
os.environ['PG_MCP_LLM_BASE_URL'] = 'https://api.deepseek.com'
os.environ['PG_MCP_LLM_MODEL'] = 'deepseek-chat'

async def test_query():
    from pg_mcp.config import ServerConfig, parse_databases_config, LLMConfig
    from pg_mcp.db.pool_manager import PoolManager
    from pg_mcp.schema.collector import SchemaCollector
    from pg_mcp.llm.client import LLMClient
    from pg_mcp.llm.schema_retriever import render_schema_context

    server_config = ServerConfig()
    llm_config = LLMConfig()
    databases = parse_databases_config(server_config)

    print(f"Databases: {list(databases.keys())}")

    # Initialize components
    pool_manager = PoolManager(server_config)
    await pool_manager.initialize()

    # Get schema
    conn = await pool_manager.acquire('pg_mcp_test')
    collector = SchemaCollector(list(databases.values())[0])
    schema = await collector.collect_full(conn)
    await pool_manager.release('pg_mcp_test', conn)

    print(f"\nSchema: {len(schema.tables)} tables")
    for t in schema.tables:
        print(f"  - {t.table_name}")

    # Test LLM with SQL generation
    print("\n--- Testing LLM ---")
    llm_client = LLMClient(
        api_key=llm_config.api_key.get_secret_value(),
        base_url=llm_config.base_url,
        model=llm_config.model,
        max_tokens=llm_config.max_tokens,
        temperature=llm_config.temperature,
    )

    # Build schema context
    schema_text = render_schema_context(schema.tables)
    print(f"Schema context: {len(schema_text)} chars")

    # Test 1: Direct SQL execution
    print("\n--- Test 1: Direct SQL ---")
    sql = "SELECT * FROM users LIMIT 3"
    conn = await pool_manager.acquire('pg_mcp_test')
    rows = await conn.fetch(sql)
    print(f"Results: {len(rows)} rows")
    for row in rows:
        print(f"  {dict(row)}")
    await pool_manager.release('pg_mcp_test', conn)

    # Test 2: LLM-generated SQL
    print("\n--- Test 2: LLM-generated SQL ---")
    system_prompt = f"""You are a SQL expert. Given the database schema and user question,
generate a SQL query. Return ONLY the SQL query, nothing else."""

    user_message = f"""Database schema:
{schema_text}

Question: 列出所有用户"""

    response = await llm_client.chat(system_prompt, user_message)
    print(f"LLM response: {response}")

    # Extract SQL from response
    sql = llm_client.extract_sql(response)
    if sql:
        print(f"\nExtracted SQL: {sql}")
        conn = await pool_manager.acquire('pg_mcp_test')
        rows = await conn.fetch(sql)
        print(f"Results: {len(rows)} rows")
        for row in rows:
            print(f"  {dict(row)}")
        await pool_manager.release('pg_mcp_test', conn)
    else:
        print("Could not extract SQL from response")

    await pool_manager.close()
    print("\nQuery test completed!")

if __name__ == "__main__":
    asyncio.run(test_query())
