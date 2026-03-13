"""Result semantic verification using LLM."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from pg_mcp.llm.prompts import VERIFICATION_SYSTEM_METADATA, VERIFICATION_SYSTEM_SAMPLE
from pg_mcp.models import QueryResult, VerificationResult

if TYPE_CHECKING:
    from pg_mcp.config import ServerConfig
    from pg_mcp.llm.client import LLMClient


class ResultVerifier:
    """Verifies query results semantically using LLM."""

    def __init__(self, config: "ServerConfig", llm_client: "LLMClient") -> None:
        self.config = config
        self.llm = llm_client

    def should_verify(self, request_verify: bool) -> bool:
        """
        Determine if verification should run.
        verify_mode=off always returns False.
        metadata/sample + request_verify=True returns True.
        """
        if self.config.verify_mode == "off":
            return False
        return request_verify

    async def verify(
        self, question: str, sql: str, result: QueryResult
    ) -> VerificationResult:
        """
        Verify whether the result correctly answers the question.
        Uses metadata or sample context based on verify_mode.
        """
        mode = self.config.verify_mode
        if mode == "metadata":
            context = self._build_metadata_context(result)
            system = VERIFICATION_SYSTEM_METADATA
        elif mode == "sample":
            context = self._build_sample_context(result)
            system = VERIFICATION_SYSTEM_SAMPLE
        else:
            return VerificationResult(
                match="unknown",
                explanation="Verification not configured",
            )

        user_message = f"Question: {question}\nSQL: {sql}\nResult info: {context}"
        response = await self.llm.chat(
            system_prompt=system,
            user_message=user_message,
        )
        return self._parse_verification(response)

    def _build_metadata_context(self, result: QueryResult) -> str:
        """Build context from columns, row count, truncated flag."""
        cols = ", ".join(f"{c.name}({c.type})" for c in result.columns)
        return (
            f"Columns: {cols}\n"
            f"Row count: {result.returned_row_count}\n"
            f"Truncated: {result.truncated}"
        )

    def _build_sample_context(self, result: QueryResult) -> str:
        """Build context from sample rows up to verify_sample_rows."""
        n = min(self.config.verify_sample_rows, len(result.rows))
        sample = result.rows[:n]
        cols = [c.name for c in result.columns]
        lines = [", ".join(cols)]
        for row in sample:
            lines.append(", ".join(str(v)[:100] for v in row))
        return "\n".join(lines)

    def _parse_verification(self, response: str) -> VerificationResult:
        """
        Parse LLM JSON response. On failure, return match="unknown".
        """
        response = response.strip()
        # Try markdown code block first
        code_match = re.search(
            r"```(?:json)?\s*\n?(.*?)```",
            response,
            re.DOTALL | re.IGNORECASE,
        )
        if code_match:
            response = code_match.group(1).strip()
        # Try parsing - first full response, then extract {...} with balanced braces
        candidates = [response]
        start = response.find("{")
        if start >= 0:
            depth = 0
            for i, c in enumerate(response[start:], start):
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        candidates.append(response[start : i + 1])
                        break
        for text in candidates:
            try:
                data = json.loads(text)
                match = str(data.get("match", "unknown")).lower()
                if match not in ("yes", "no", "partial"):
                    match = "unknown"
                return VerificationResult(
                    match=match,
                    explanation=str(data.get("explanation", "")) or "No explanation",
                    suggested_sql=data.get("suggested_sql") or None,
                )
            except (json.JSONDecodeError, TypeError):
                pass
        return VerificationResult(
            match="unknown",
            explanation="Could not parse LLM verification response",
        )
