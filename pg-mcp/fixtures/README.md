# pg-mcp Test Database Fixtures

Three PostgreSQL databases for testing schema discovery, NLQ (Natural Language Query), and RAG retrieval per PRD FR-2.1.1.

## Databases

| Database       | Scale   | Tables | Views | Types (enum/composite) | Indexes | Rows (approx) |
| -------------- | ------- | ------ | ----- | ----------------------- | ------- | ------------- |
| `pg_mcp_small` | Minimal | 6      | 2     | 2                       | 8       | ~100          |
| `pg_mcp_medium`| Medium  | 21     | 8     | 6                       | 25+     | ~150          |
| `pg_mcp_large` | Large   | ~220   | 35    | 12                      | 100+    | ~10k          |

### pg_mcp_small

E-commerce: users, products, categories, orders, order_items. Simple FKs, two enum types. For basic schema collector and NLQ smoke tests.

### pg_mcp_medium

Multi-schema: `public` (e-commerce), `hr` (employees, departments, salaries, attendance), `projects` (projects, tasks, milestones), `analytics` (daily_metrics). Composite type `address_t`, multiple enums. For schema retrieval across schemas and RAG budget testing.

### pg_mcp_large

Enterprise-style: `public`, `sales`, `inventory`, `finance`, `logistics`, `catalog`. ~150 generated `entity_N` tables plus core tables. For `max_tables_per_db` truncation and schema retrieval budget stress testing.

## Rebuild (Windows PowerShell)

```powershell
cd pg-mcp\fixtures

# Rebuild all three
.\rebuild.ps1

# Rebuild one
.\rebuild.ps1 small
.\rebuild.ps1 medium
.\rebuild.ps1 large

# Drop all
.\rebuild.ps1 clean

# Help
.\rebuild.ps1 -Help
```

## Environment

| Variable  | Default   | Description           |
| --------- | --------- | --------------------- |
| PGHOST    | localhost | PostgreSQL host       |
| PGPORT    | 5432      | PostgreSQL port       |
| PGUSER    | postgres  | Superuser for DDL     |
| PGPASSWORD| 123456    | Password (if needed)   |
| PGBIN     | —         | Path to psql.exe if not in PATH. Script auto-detects `D:\Program Files\PostgreSQL\bin` and `C:\Program Files\PostgreSQL\*\bin` |

Example:

```powershell
$env:PGHOST="localhost"
$env:PGPORT="5432"
$env:PGUSER="postgres"
$env:PGPASSWORD="123456"
.\rebuild.ps1 small
```

## Connection Strings (Read-Only User)

After creating a read-only user for pg-mcp tests:

```
postgresql://readonly:pass@localhost:5432/pg_mcp_small
postgresql://readonly:pass@localhost:5432/pg_mcp_medium
postgresql://readonly:pass@localhost:5432/pg_mcp_large
```
