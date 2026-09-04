"""Optional local cross-encoder used only after first-stage hybrid retrieval."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


class FastEmbedCrossEncoder:
    """Thin lazy-loading wrapper that keeps the retrieval service testable."""

    def __init__(self, model_name: str, cache_dir: Path | str) -> None:
        self.model_name = model_name
        self.cache_dir = str(cache_dir)
        self._model = None

    @property
    def implementation(self) -> str:
        return "fastembed-cross-encoder-0.8"

    def score(self, query: str, documents: Iterable[str]) -> list[float]:
        if self._model is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            self._model = TextCrossEncoder(
                model_name=self.model_name,
                cache_dir=self.cache_dir,
            )
        return [float(value) for value in self._model.rerank(query, list(documents))]
