"""LLM client wrapper (OpenAI SDK, DeepSeek compatible)."""

from __future__ import annotations

import re

from openai import AsyncOpenAI

from pg_mcp.errors import LLMError, LLMParseError


class LLMClient:
    """Async OpenAI-compatible client for SQL generation and verification."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature

    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int | None = None,
    ) -> str:
        """
        Send chat completion request.
        Raises LLMError on API failure, LLMParseError on invalid response.
        """
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=max_tokens or self._max_tokens,
                temperature=self._temperature,
            )
        except Exception as e:
            raise LLMError(str(e), retryable=True) from e

        if not response.choices:
            raise LLMParseError("Empty response from LLM")

        content = response.choices[0].message.content
        if content is None:
            raise LLMParseError("No content in LLM response")
        return content.strip()

    def extract_sql(self, response: str) -> str:
        """
        Extract SQL from LLM response.
        Looks for ```sql...``` block first; otherwise uses full text.
        Raises LLMParseError if extraction fails.
        """
        response = response.strip()
        if not response:
            raise LLMParseError("Empty LLM response")

        match = re.search(
            r"```(?:sql)?\s*\n(.*?)```",
            response,
            re.DOTALL | re.IGNORECASE,
        )
        if match:
            sql = match.group(1).strip()
        else:
            sql = response

        if not sql or not sql.strip():
            raise LLMParseError("Could not extract SQL from LLM response")
        return sql
