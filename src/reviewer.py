"""Wrapper around the Anthropic API — one call per review."""

from __future__ import annotations

from anthropic import Anthropic

# Use Opus 4.6 with 1M context beta (same price as 200K at current tier).
_MODEL = "claude-opus-4-6"
_CONTEXT_1M_BETA = "context-1m-2025-08-07"
_MAX_OUTPUT_TOKENS = 8000  # plenty for a review comment; stays well under SDK timeout


class Reviewer:
    def __init__(self, api_key: str):
        self._client = Anthropic(api_key=api_key)

    def review(self, system_prompt: str, user_content: str) -> str:
        """Run one review pass. Returns the model's text output (not including thinking)."""
        response = self._client.beta.messages.create(
            model=_MODEL,
            max_tokens=_MAX_OUTPUT_TOKENS,
            betas=[_CONTEXT_1M_BETA],
            thinking={"type": "adaptive"},
            output_config={"effort": "max"},
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )

        # Extract only text blocks (skip thinking blocks etc.)
        text_parts: list[str] = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
        return "".join(text_parts).strip()
