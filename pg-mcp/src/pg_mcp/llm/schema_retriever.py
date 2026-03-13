"""Schema retrieval for LLM context (keyword-based relevance)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pg_mcp.schema.models import DatabaseSchema, TableInfo


def _tokenize(question: str) -> list[str]:
    """Extract lowercase tokens from question for matching."""
    text = question.lower()
    tokens = re.findall(r"\b\w+\b", text)
    return [t for t in tokens if len(t) > 1]


def _score_table(tokens: list[str], table: "TableInfo") -> float:
    """Score how relevant a table is to the question tokens."""
    score = 0.0
    searchable = (
        table.table_name.lower()
        + " "
        + " ".join(c.name.lower() for c in table.columns)
        + " "
        + (table.comment or "").lower()
    )
    for token in tokens:
        if token in searchable:
            score += 1.0
        if token in table.table_name.lower():
            score += 2.0
    return score


def render_schema_context(tables: list["TableInfo"]) -> str:
    """Render selected tables as schema context string."""
    parts: list[str] = []
    for t in tables:
        cols = ", ".join(
            f"{c.name} {c.type}{'(PK)' if c.is_primary_key else ''}"
            for c in t.columns
        )
        line = f"{t.schema_name}.{t.table_name} ({cols})"
        if t.comment:
            line += f"  -- {t.comment[:500]}"
        parts.append(line)
        for fk in t.foreign_keys:
            parts.append(
                f"  FK: {fk.source_column} → {fk.target_table}.{fk.target_column}"
            )
    return "\n".join(parts)


class SchemaRetriever:
    """Finds relevant tables for a question within a character budget."""

    def __init__(self, max_context_chars: int = 8000) -> None:
        self.max_context_chars = max_context_chars

    def find_relevant_tables(
        self,
        question: str,
        schema: "DatabaseSchema",
    ) -> list["TableInfo"]:
        """
        Return tables ranked by relevance to the question.
        Falls back to first 10 tables if no match.
        """
        tokens = _tokenize(question)
        scored: list[tuple[float, "TableInfo"]] = []
        for table in schema.tables:
            score = _score_table(tokens, table)
            if score > 0:
                scored.append((score, table))
        scored.sort(key=lambda x: x[0], reverse=True)

        selected: list["TableInfo"] = []
        budget = self.max_context_chars
        for score, table in scored:
            rendered = render_schema_context([table])
            if len(rendered) > budget:
                break
            selected.append(table)
            budget -= len(rendered)

        if not selected and schema.tables:
            # Fallback: take first tables up to budget
            for table in schema.tables[:10]:
                rendered = render_schema_context([table])
                if len(rendered) > budget:
                    break
                selected.append(table)
                budget -= len(rendered)

        return selected
