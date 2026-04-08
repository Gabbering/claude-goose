"""Wrapper around the Anthropic API — one call per review.

Designed to work against either:
- The official Anthropic API (no `ANTHROPIC_BASE_URL` set), or
- An Anthropic-compatible third-party proxy (set `ANTHROPIC_BASE_URL`).

Beta features (1M context, adaptive thinking, effort=max) are NOT used because
most third-party proxies don't implement them.
"""

from __future__ import annotations

import os

from anthropic import Anthropic

# Default model. Override via the CLAUDE_MODEL env var if your proxy only
# carries sonnet (or anything else).
_DEFAULT_MODEL = "claude-opus-4-6"

_MAX_OUTPUT_TOKENS = 8000   # plenty for a review comment; well under SDK timeout
_TEMPERATURE = 0.5          # leave some room for goose personality, not chaotic


class Reviewer:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        model: str | None = None,
    ):
        client_kwargs: dict = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = Anthropic(**client_kwargs)
        self._model = model or _DEFAULT_MODEL

    def review(self, system_prompt: str, user_content: str) -> str:
        """Run one review pass. Returns the model's text output."""
        response = self._client.messages.create(
            model=self._model,
            max_tokens=_MAX_OUTPUT_TOKENS,
            temperature=_TEMPERATURE,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )

        # Extract text blocks. (No beta features → no thinking blocks to skip,
        # but we still iterate defensively in case the proxy returns weird shapes.)
        text_parts: list[str] = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
        return "".join(text_parts).strip()


def reviewer_from_env(api_key: str) -> Reviewer:
    """Build a Reviewer using ANTHROPIC_BASE_URL and CLAUDE_MODEL from env."""
    return Reviewer(
        api_key=api_key,
        base_url=os.environ.get("ANTHROPIC_BASE_URL") or None,
        model=os.environ.get("CLAUDE_MODEL") or None,
    )
