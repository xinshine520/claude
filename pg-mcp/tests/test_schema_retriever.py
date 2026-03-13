"""Unit tests for schema retriever."""

from __future__ import annotations

import pytest

from pg_mcp.llm.schema_retriever import (
    SchemaRetriever,
    _score_table,
    _tokenize,
    render_schema_context,
)
from pg_mcp.schema.models import (
    ColumnInfo,
    DatabaseSchema,
    ForeignKeyInfo,
    TableInfo,
)


@pytest.fixture
def sample_schema():
    """Minimal schema with a few tables."""
    users = TableInfo(
        schema_name="public",
        table_name="users",
        table_type="table",
        columns=[
            ColumnInfo(name="id", type="int4", nullable=False, is_primary_key=True),
            ColumnInfo(name="name", type="text", nullable=False),
            ColumnInfo(name="email", type="text", nullable=True),
        ],
        comment="Registered users",
    )
    orders = TableInfo(
        schema_name="public",
        table_name="orders",
        table_type="table",
        columns=[
            ColumnInfo(name="id", type="int4", nullable=False, is_primary_key=True),
            ColumnInfo(name="user_id", type="int4", nullable=False),
            ColumnInfo(name="total", type="numeric", nullable=False),
        ],
        foreign_keys=[
            ForeignKeyInfo(
                constraint_name="fk_user",
                source_column="user_id",
                target_table="users",
                target_column="id",
            )
        ],
    )
    products = TableInfo(
        schema_name="public",
        table_name="products",
        table_type="table",
        columns=[
            ColumnInfo(name="id", type="int4", nullable=False),
            ColumnInfo(name="name", type="text", nullable=False),
        ],
    )
    return DatabaseSchema(
        database_name="test",
        schemas=["public"],
        tables=[users, orders, products],
        collected_at="2026-01-01T00:00:00Z",
    )


def test_tokenize():
    """_tokenize extracts words."""
    assert _tokenize("How many users?") == ["how", "many", "users"]
    assert _tokenize("list all orders") == ["list", "all", "orders"]


def test_score_table_exact_match():
    """Exact table name match scores highest."""
    table = TableInfo(
        schema_name="public",
        table_name="users",
        table_type="table",
        columns=[ColumnInfo(name="id", type="int", nullable=False)],
    )
    score = _score_table(["users"], table)
    assert score > 0
    assert score >= 2.0  # table name match gives +2


def test_score_table_column_match():
    """Column name match adds score."""
    table = TableInfo(
        schema_name="public",
        table_name="orders",
        table_type="table",
        columns=[ColumnInfo(name="total", type="numeric", nullable=False)],
    )
    score = _score_table(["total"], table)
    assert score >= 1.0


def test_score_table_no_match():
    """No matching tokens returns 0."""
    table = TableInfo(
        schema_name="public",
        table_name="xyz",
        table_type="table",
        columns=[],
    )
    assert _score_table(["users", "orders"], table) == 0.0


def test_render_schema_context():
    """render_schema_context formats tables correctly."""
    table = TableInfo(
        schema_name="public",
        table_name="users",
        table_type="table",
        columns=[
            ColumnInfo(name="id", type="int", nullable=False, is_primary_key=True),
            ColumnInfo(name="name", type="text", nullable=False),
        ],
    )
    out = render_schema_context([table])
    assert "public.users" in out
    assert "id int(PK)" in out
    assert "name text" in out


def test_find_relevant_tables_exact_match(sample_schema):
    """Exact table name gets selected."""
    retriever = SchemaRetriever(max_context_chars=10000)
    tables = retriever.find_relevant_tables("show users", sample_schema)
    assert any(t.table_name == "users" for t in tables)
    assert len(tables) >= 1


def test_find_relevant_tables_fallback_when_no_match(sample_schema):
    """Fallback to first 10 tables when no token match."""
    retriever = SchemaRetriever(max_context_chars=10000)
    tables = retriever.find_relevant_tables("xyzzy quux", sample_schema)
    assert len(tables) <= 10
    assert len(tables) > 0
    assert tables == sample_schema.tables[: len(tables)]


def test_find_relevant_tables_budget_truncation(sample_schema):
    """Tables are truncated when exceeding char budget."""
    retriever = SchemaRetriever(max_context_chars=50)
    tables = retriever.find_relevant_tables("users", sample_schema)
    rendered = render_schema_context(tables)
    assert len(rendered) <= 100  # allow some slack for small schemas


def test_find_relevant_tables_empty_schema():
    """Empty schema returns empty list."""
    retriever = SchemaRetriever()
    schema = DatabaseSchema(
        database_name="empty",
        schemas=[],
        tables=[],
        collected_at="2026-01-01T00:00:00Z",
    )
    tables = retriever.find_relevant_tables("anything", schema)
    assert tables == []
