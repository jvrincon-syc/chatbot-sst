from __future__ import annotations

from collections.abc import Sequence

import tiktoken

from chunking.application.ports import TokenCounterPort


class CanonicalTokenizer(TokenCounterPort):
    """Canonical local tokenizer for deterministic chunk sizing."""

    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        self._encoding_name = encoding_name
        self._encoding = tiktoken.get_encoding(encoding_name)

    @property
    def encoding_name(self) -> str:
        """Return the configured encoding identity."""
        return self._encoding_name

    def encode(self, text: str) -> list[int]:
        """Return canonical token ids for the supplied text."""
        return list(self._encoding.encode(text))

    def count_tokens(self, text: str) -> int:
        """Return the canonical token count for the supplied text."""
        return len(self.encode(text))

    def decode(self, token_ids: Sequence[int]) -> str:
        """Decode token ids back to canonical text."""
        return self._encoding.decode(list(token_ids))
