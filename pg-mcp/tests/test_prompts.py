"""Unit tests for prompt templates."""

from __future__ import annotations

import pytest

from pg_mcp.llm import prompts


def test_build_sql_generation_prompt():
    """build_sql_generation_prompt includes schema and question."""
    system, user = prompts.build_sql_generation_prompt(
        question="How many users?",
        schema_context="public.users (id int, name text)",
    )
    assert "How many users?" in user
    assert "public.users" in system
    assert "Rules:" in system
    assert "SELECT" in system


def test_build_verification_prompt_metadata():
    """build_verification_prompt with metadata mode."""
    system, user = prompts.build_verification_prompt(
        question="Count users",
        sql="SELECT COUNT(*) FROM users",
        context="Columns: count\nRow count: 1",
        mode="metadata",
    )
    assert "metadata" in system.lower() or "validator" in system.lower()
    assert "Count users" in user
    assert "SELECT COUNT" in user
    assert "Result info" in user


def test_build_verification_prompt_sample():
    """build_verification_prompt with sample mode."""
    system, user = prompts.build_verification_prompt(
        question="List users",
        sql="SELECT * FROM users",
        context="id, name\n1, alice",
        mode="sample",
    )
    assert "Count users" not in user
    assert "List users" in user
    assert "SELECT *" in user


def test_build_db_selection_prompt():
    """build_db_selection_prompt includes summaries and question."""
    system, user = prompts.build_db_selection_prompt(
        question="Query sales data",
        db_summaries="mydb: 10 tables, sales: 5 tables",
    )
    assert "mydb" in system
    assert "sales" in system
    assert "Query sales data" in user


def test_sql_generation_system_has_rules():
    """SQL_GENERATION_SYSTEM contains key rules."""
    assert "SELECT" in prompts.SQL_GENERATION_SYSTEM
    assert "INSERT" in prompts.SQL_GENERATION_SYSTEM or "DDL" in prompts.SQL_GENERATION_SYSTEM
    assert "pg_sleep" in prompts.SQL_GENERATION_SYSTEM
    assert "{schema_context}" in prompts.SQL_GENERATION_SYSTEM


def test_db_selection_system_has_placeholder():
    """DB_SELECTION_SYSTEM has db_summaries placeholder."""
    assert "{db_summaries}" in prompts.DB_SELECTION_SYSTEM
