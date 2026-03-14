import asyncio
import asyncpg

async def setup():
    conn = await asyncpg.connect(
        host='127.0.0.1',
        port=5432,
        user='postgres',
        password='123456',
        database='pg_mcp_test'
    )

    # Drop all existing tables
    tables = ['order_items', 'products', 'categories', 'orders', 'users', 'departments']
    for table in tables:
        try:
            await conn.execute(f'DROP TABLE IF EXISTS {table} CASCADE')
            print(f'Dropped {table}')
        except Exception as e:
            print(f'Error dropping {table}: {e}')

    # Read seed.sql and remove psql commands
    with open('tests/fixtures/seed.sql', 'r', encoding='utf-8') as f:
        content = f.read()

    # Remove psql commands
    lines = []
    for line in content.split('\n'):
        if line.strip().startswith('\\') or line.strip().startswith('--'):
            continue
        lines.append(line)

    sql = '\n'.join(lines)

    # Execute entire SQL
    await conn.execute(sql)
    print('Tables and data created')

    # Check tables
    tables = await conn.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"
    )
    print(f'Tables: {[t["table_name"] for t in tables]}')

    # Check row counts
    for table in ['categories', 'users', 'departments', 'products', 'orders', 'order_items']:
        count = await conn.fetchval(f'SELECT COUNT(*) FROM {table}')
        print(f'{table}: {count} rows')

    await conn.close()

asyncio.run(setup())
