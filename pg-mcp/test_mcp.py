"""Test script to verify pg-mcp is working."""
import asyncio
import os

# Set environment variables before importing
os.environ['PG_MCP_DATABASES'] = 'pg_mcp_test'
os.environ['PG_MCP_PG_MCP_TEST_URL'] = 'postgresql://postgres:123456@127.0.0.1:5432/pg_mcp_test'
os.environ['PG_MCP_LLM_API_KEY'] = 'sk-eb62d7185a224320b44fc2929928dcac'
os.environ['PG_MCP_LLM_BASE_URL'] = 'https://api.deepseek.com'
os.environ['PG_MCP_LLM_MODEL'] = 'deepseek-chat'

async def test_mcp():
    # Import MCP components
    from pg_mcp.config import ServerConfig, parse_databases_config

    # Create config
    server_config = ServerConfig()
    databases = parse_databases_config(server_config)
    print(f"Databases: {list(databases.keys())}")

    from pg_mcp.db.pool_manager import PoolManager
    pool_manager = PoolManager(server_config)
    await pool_manager.initialize()

    # Test a simple query - list tables
    from pg_mcp.schema.collector import SchemaCollector

    for db_name, db_config in databases.items():
        conn = await pool_manager.acquire(db_name)
        collector = SchemaCollector(db_config)
        schema = await collector.collect_full(conn)
        print(f"\nDatabase '{db_name}' schema:")
        print(f"  Tables: {len(schema.tables)}")
        for table in schema.tables[:10]:
            print(f"    - {table.table_name} ({len(table.columns)} columns)")
            for col in table.columns[:3]:
                print(f"        - {col.name}: {col.type}")
        await pool_manager.release(db_name, conn)

    await pool_manager.close()
    print("\nMCP connection test passed!")

if __name__ == "__main__":
    asyncio.run(test_mcp())
