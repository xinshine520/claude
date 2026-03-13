"""Prompt templates for SQL generation and verification."""

from __future__ import annotations


SQL_GENERATION_SYSTEM = """You are a PostgreSQL SQL expert. Your task is to generate
a single read-only SQL query based on the user's question and the database schema
provided below.

Rules:
- Generate ONLY a single SELECT statement (CTEs with WITH are allowed).
- Do NOT use INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, or any DDL/DML.
- Do NOT use functions like pg_sleep, dblink, lo_export, set_config.
- Output ONLY the raw SQL statement, no markdown fences, no explanations.

Database schema:
{schema_context}
"""

SQL_GENERATION_USER = """Question: {question}"""

VERIFICATION_SYSTEM_METADATA = """You are a query result validator. Given a user's
question, the generated SQL, and result metadata, assess whether the query correctly
answers the question.

Respond in JSON: {"match": "yes|no|partial", "explanation": "...", "suggested_sql": "..."}
"""

VERIFICATION_SYSTEM_SAMPLE = """You are a query result validator. Given a user's
question, the generated SQL, and a sample of the result rows, assess whether the query
correctly answers the question.

Respond in JSON: {"match": "yes|no|partial", "explanation": "...", "suggested_sql": "..."}
"""

DB_SELECTION_SYSTEM = """Given the user's question and the following database summaries,
select the most relevant database. Respond with ONLY the database alias name.

Databases:
{db_summaries}
"""


def build_sql_generation_prompt(
    question: str,
    schema_context: str,
) -> tuple[str, str]:
    """Build system and user prompts for SQL generation."""
    system = SQL_GENERATION_SYSTEM.format(schema_context=schema_context)
    user = SQL_GENERATION_USER.format(question=question)
    return system, user


def build_verification_prompt(
    question: str,
    sql: str,
    context: str,
    mode: str = "metadata",
) -> tuple[str, str]:
    """Build system and user prompts for result verification."""
    system = (
        VERIFICATION_SYSTEM_METADATA
        if mode == "metadata"
        else VERIFICATION_SYSTEM_SAMPLE
    )
    user = f"Question: {question}\nSQL: {sql}\nResult info: {context}"
    return system, user


def build_db_selection_prompt(
    question: str,
    db_summaries: str,
) -> tuple[str, str]:
    """Build system and user prompts for database selection."""
    system = DB_SELECTION_SYSTEM.format(db_summaries=db_summaries)
    user = f"Question: {question}"
    return system, user
