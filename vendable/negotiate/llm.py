"""OpenAI adapter for the `Completer` protocol.

Kept deliberately thin, and kept separate from `agent.py`, so that every test of negotiation
logic runs against a stub with no key and no network. The provider is an implementation
detail of one method; swapping it should not touch a single line of policy code.
"""

from __future__ import annotations

import time

from vendable.core.settings import Settings
from vendable.core.settings import settings as default_settings


class LLMUnavailable(RuntimeError):
    """The model could not be reached. Callers fall back to a deterministic path."""


class OpenAICompleter:
    """Single-turn completion. No tools, no memory, no streaming.

    The negotiation agent deliberately does not give the model conversation state: each turn
    is re-derived from the line item and the policy authority, so there is no accumulated
    context for an injection to hide in across turns.
    """

    def __init__(
        self,
        cfg: Settings | None = None,
        *,
        model: str | None = None,
        max_retries: int = 2,
        timeout_s: float = 60.0,
    ) -> None:
        self.cfg = cfg or default_settings
        if not self.cfg.llm_configured:
            raise LLMUnavailable("No OPENAI_API_KEY configured. See .env.example.")
        self.model = model or self.cfg.openai_model
        self.max_retries = max_retries
        self.timeout_s = timeout_s
        self._client = None

    def _lazy_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self.cfg.openai_api_key, timeout=self.timeout_s)
        return self._client

    def complete(self, system: str, user: str) -> str:
        client = self._lazy_client()
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={"type": "json_object"},
                )
                return (resp.choices[0].message.content or "").strip()
            except Exception as exc:  # noqa: BLE001 -- provider errors are not a taxonomy
                last = exc
                if attempt < self.max_retries:
                    time.sleep(0.5 * (2**attempt))
        raise LLMUnavailable(f"OpenAI call failed after {self.max_retries + 1} attempts: {last}")


__all__ = ["LLMUnavailable", "OpenAICompleter"]
