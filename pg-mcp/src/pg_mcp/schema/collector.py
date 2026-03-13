"""Schema metadata collector from PostgreSQL."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import asyncpg

from pg_mcp.schema.models import (
    ColumnInfo,
    DatabaseSchema,
    EnumTypeInfo,
    ForeignKeyInfo,
    IndexInfo,
    TableInfo,
)


class SchemaCollector:
    """Collects database schema metadata from PostgreSQL."""

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
            ON pgd.objoid = st.relid AND pgd.objsubid = c.ordinal_position
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
            AND tc.table_schema = kcu.table_schema AND tc.table_name = kcu.table_name
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY tc.table_schema, tc.table_name, kcu.ordinal_position
    """

    INDEXES_QUERY = """
        SELECT indexname AS index_name, tablename AS table_name,
               schemaname AS schema_name, indexdef
        FROM pg_catalog.pg_indexes
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
        ORDER BY schemaname, tablename, indexname
    """

    ENUM_TYPES_QUERY = """
        SELECT t.typname AS type_name, n.nspname AS schema_name,
               array_agg(e.enumlabel ORDER BY e.enumsortorder) AS values
        FROM pg_catalog.pg_type t
        JOIN pg_catalog.pg_namespace n ON t.typnamespace = n.oid
        JOIN pg_catalog.pg_enum e ON t.oid = e.enumtypid
        WHERE t.typtype = 'e'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        GROUP BY t.typname, n.nspname
    """

    VIEW_DEFINITIONS_QUERY = """
        SELECT table_schema, table_name, view_definition
        FROM information_schema.views
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
        ORDER BY table_schema, table_name
    """

    PRIMARY_KEYS_QUERY = """
        SELECT tc.table_schema, tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema AND tc.table_name = kcu.table_name
        WHERE tc.constraint_type = 'PRIMARY KEY'
          AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')
    """

    TABLE_COMMENTS_QUERY = """
        SELECT c.relnamespace::regnamespace::text AS schema_name,
               c.relname AS table_name,
               pgd.description AS comment
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
        LEFT JOIN pg_catalog.pg_description pgd
            ON pgd.objoid = c.oid AND pgd.objsubid = 0
        WHERE c.relkind IN ('r', 'v', 'm')
          AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
    """

    def __init__(self, collect_view_definitions: bool = True) -> None:
        self.collect_view_definitions = collect_view_definitions

    async def collect_full(
        self,
        conn: asyncpg.Connection,
        database_name: str = "unknown",
    ) -> DatabaseSchema:
        """Collect full schema metadata for a database."""
        tables_raw: list[asyncpg.Record] = []
        columns_raw: list[asyncpg.Record] = []
        fk_raw: list[asyncpg.Record] = []
        indexes_raw: list[asyncpg.Record] = []
        enums_raw: list[asyncpg.Record] = []
        views_raw: list[asyncpg.Record] = []
        pk_raw: list[asyncpg.Record] = []
        table_comments_raw: list[asyncpg.Record] = []

        try:
            tables_raw = await conn.fetch(self.TABLES_QUERY)
        except Exception:
            pass
        try:
            columns_raw = await conn.fetch(self.COLUMNS_QUERY)
        except Exception:
            pass
        try:
            fk_raw = await conn.fetch(self.FOREIGN_KEYS_QUERY)
        except Exception:
            pass
        try:
            indexes_raw = await conn.fetch(self.INDEXES_QUERY)
        except Exception:
            pass
        try:
            enums_raw = await conn.fetch(self.ENUM_TYPES_QUERY)
        except Exception:
            pass
        if self.collect_view_definitions:
            try:
                views_raw = await conn.fetch(self.VIEW_DEFINITIONS_QUERY)
            except Exception:
                pass
        try:
            pk_raw = await conn.fetch(self.PRIMARY_KEYS_QUERY)
        except Exception:
            pass
        try:
            table_comments_raw = await conn.fetch(self.TABLE_COMMENTS_QUERY)
        except Exception:
            pass

        return self._assemble(
            database_name=database_name,
            tables_raw=tables_raw,
            columns_raw=columns_raw,
            fk_raw=fk_raw,
            indexes_raw=indexes_raw,
            enums_raw=enums_raw,
            views_raw=views_raw,
            pk_raw=pk_raw,
            table_comments_raw=table_comments_raw,
        )

    def _assemble(
        self,
        *,
        database_name: str,
        tables_raw: list[asyncpg.Record],
        columns_raw: list[asyncpg.Record],
        fk_raw: list[asyncpg.Record],
        indexes_raw: list[asyncpg.Record],
        enums_raw: list[asyncpg.Record],
        views_raw: list[asyncpg.Record],
        pk_raw: list[asyncpg.Record],
        table_comments_raw: list[asyncpg.Record],
    ) -> DatabaseSchema:
        schemas_set: set[str] = set()
        tables_by_key: dict[tuple[str, str], TableInfo] = {}
        pk_set: set[tuple[str, str, str]] = set()
        view_defs: dict[tuple[str, str], str] = {}
        table_comments: dict[tuple[str, str], str] = {}

        for r in pk_raw:
            schema = str(r.get("table_schema", ""))
            table = str(r.get("table_name", ""))
            col = str(r.get("column_name", ""))
            pk_set.add((schema, table, col))

        for r in views_raw:
            schema = str(r.get("table_schema", ""))
            table = str(r.get("table_name", ""))
            defn = r.get("view_definition") or ""
            view_defs[(schema, table)] = defn

        for r in table_comments_raw:
            schema = str(r.get("schema_name", "")).split(".")[-1]
            table = str(r.get("table_name", ""))
            comment = r.get("comment")
            if comment:
                table_comments[(schema, table)] = str(comment)

        for r in tables_raw:
            schema = str(r.get("table_schema", ""))
            table = str(r.get("table_name", ""))
            tbl_type = str(r.get("table_type", "BASE TABLE")).lower()
            if "view" in tbl_type:
                tbl_type = "view"
            else:
                tbl_type = "table"
            schemas_set.add(schema)
            tables_by_key[(schema, table)] = TableInfo(
                schema_name=schema,
                table_name=table,
                table_type=tbl_type,
                columns=[],
                foreign_keys=[],
                indexes=[],
                comment=table_comments.get((schema, table)),
                view_definition=view_defs.get((schema, table)),
                row_estimate=None,
            )

        cols_by_table: dict[tuple[str, str], list[ColumnInfo]] = {}
        for r in columns_raw:
            schema = str(r.get("table_schema", ""))
            table = str(r.get("table_name", ""))
            col_name = str(r.get("column_name", ""))
            data_type = str(r.get("data_type", ""))
            is_nullable = str(r.get("is_nullable", "YES")).upper() == "YES"
            default = r.get("column_default")
            comment = r.get("comment")
            is_pk = (schema, table, col_name) in pk_set
            col = ColumnInfo(
                name=col_name,
                type=data_type,
                nullable=is_nullable,
                is_primary_key=is_pk,
                default=str(default) if default else None,
                comment=str(comment) if comment else None,
            )
            key = (schema, table)
            cols_by_table.setdefault(key, []).append(col)

        for key, cols in cols_by_table.items():
            if key in tables_by_key:
                tables_by_key[key].columns = cols

        for r in fk_raw:
            schema = str(r.get("table_schema", ""))
            table = str(r.get("table_name", ""))
            target_schema = str(r.get("target_schema", ""))
            target_table = str(r.get("target_table", ""))
            target_col = str(r.get("target_column", ""))
            fk = ForeignKeyInfo(
                constraint_name=str(r.get("constraint_name", "")),
                source_column=str(r.get("column_name", "")),
                target_table=f"{target_schema}.{target_table}" if target_schema != "public" else target_table,
                target_column=target_col,
            )
            if (schema, table) in tables_by_key:
                tables_by_key[(schema, table)].foreign_keys.append(fk)

        for r in indexes_raw:
            schema = str(r.get("schema_name", ""))
            table = str(r.get("table_name", ""))
            indexdef = str(r.get("indexdef", ""))
            index_name = str(r.get("index_name", ""))
            index_type, columns = self._parse_index_def(indexdef)
            is_unique = "UNIQUE" in indexdef.upper()
            idx = IndexInfo(
                name=index_name,
                columns=columns,
                index_type=index_type,
                is_unique=is_unique,
            )
            if (schema, table) in tables_by_key:
                tables_by_key[(schema, table)].indexes.append(idx)

        enum_types = []
        for r in enums_raw:
            schema = str(r.get("schema_name", ""))
            type_name = str(r.get("type_name", ""))
            values = r.get("values")
            if isinstance(values, list):
                vals = [str(v) for v in values]
            elif hasattr(values, "__iter__"):
                vals = [str(v) for v in values]
            else:
                vals = []
            enum_types.append(
                EnumTypeInfo(
                    schema_name=schema,
                    type_name=type_name,
                    values=vals,
                )
            )

        tables = list(tables_by_key.values())
        tables.sort(key=lambda t: (t.schema_name, t.table_name))

        return DatabaseSchema(
            database_name=database_name,
            schemas=sorted(schemas_set),
            tables=tables,
            enum_types=enum_types,
            collected_at=datetime.now(timezone.utc).isoformat(),
        )

    def _parse_index_def(self, indexdef: str) -> tuple[str, list[str]]:
        """Parse indexdef to extract index type and column names."""
        index_type = "btree"
        if "USING gin" in indexdef.lower():
            index_type = "gin"
        elif "USING gist" in indexdef.lower():
            index_type = "gist"
        elif "USING hash" in indexdef.lower():
            index_type = "hash"
        elif "USING btree" in indexdef.lower():
            index_type = "btree"

        columns: list[str] = []
        match = re.search(r"\(([^)]+)\)", indexdef)
        if match:
            col_part = match.group(1)
            for part in re.split(r",\s*", col_part):
                part = part.strip()
                if " " in part:
                    part = part.split()[0]
                part = part.strip('"')
                if part:
                    columns.append(part)
        return index_type, columns

    async def collect_summary(self, conn: asyncpg.Connection) -> dict[str, Any]:
        """Collect schema summary (for warm-up)."""
        result = await conn.fetch("""
            SELECT table_schema, table_type, COUNT(*)::int AS cnt
            FROM information_schema.tables
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
            GROUP BY table_schema, table_type
            ORDER BY table_schema, table_type
        """)
        summary: dict[str, Any] = {
            "by_schema": {},
            "total_tables": 0,
            "total_views": 0,
        }
        for r in result:
            schema = str(r.get("table_schema", ""))
            tbl_type = str(r.get("table_type", ""))
            cnt = int(r.get("cnt", 0))
            if schema not in summary["by_schema"]:
                summary["by_schema"][schema] = {"tables": 0, "views": 0}
            if "VIEW" in tbl_type.upper():
                summary["by_schema"][schema]["views"] += cnt
                summary["total_views"] += cnt
            else:
                summary["by_schema"][schema]["tables"] += cnt
                summary["total_tables"] += cnt
        return summary
