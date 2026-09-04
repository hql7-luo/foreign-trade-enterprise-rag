from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any

from app.text import tokenize


@dataclass(frozen=True)
class SparseVectorData:
    indices: list[int]
    values: list[float]


@dataclass
class BM25Encoder:
    vocabulary: dict[str, int]
    idf: dict[str, float]
    average_document_length: float
    k1: float = 1.5
    b: float = 0.75

    @classmethod
    def fit(cls, documents: list[str]) -> BM25Encoder:
        if not documents:
            raise ValueError("BM25 requires at least one document")
        tokenized = [tokenize(document) for document in documents]
        document_frequency: Counter[str] = Counter()
        for tokens in tokenized:
            document_frequency.update(set(tokens))
        vocabulary = {term: index for index, term in enumerate(sorted(document_frequency))}
        count = len(documents)
        idf = {
            term: math.log(1.0 + (count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }
        average_length = sum(len(tokens) for tokens in tokenized) / count
        return cls(vocabulary=vocabulary, idf=idf, average_document_length=average_length)

    def encode_document(self, text: str) -> SparseVectorData:
        tokens = tokenize(text)
        frequencies = Counter(tokens)
        document_length = max(len(tokens), 1)
        indices: list[int] = []
        values: list[float] = []
        for term, frequency in sorted(
            frequencies.items(), key=lambda item: self.vocabulary.get(item[0], -1)
        ):
            index = self.vocabulary.get(term)
            if index is None:
                continue
            denominator = frequency + self.k1 * (
                1 - self.b + self.b * document_length / max(self.average_document_length, 1.0)
            )
            score = self.idf[term] * (frequency * (self.k1 + 1)) / denominator
            indices.append(index)
            values.append(score)
        return SparseVectorData(indices=indices, values=values)

    def encode_query(self, text: str) -> SparseVectorData:
        frequencies = Counter(tokenize(text))
        pairs = [
            (self.vocabulary[term], 1.0 + math.log(frequency))
            for term, frequency in frequencies.items()
            if term in self.vocabulary
        ]
        pairs.sort()
        return SparseVectorData(
            indices=[pair[0] for pair in pairs],
            values=[pair[1] for pair in pairs],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "vocabulary": self.vocabulary,
            "idf": self.idf,
            "average_document_length": self.average_document_length,
            "k1": self.k1,
            "b": self.b,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> BM25Encoder:
        return cls(
            vocabulary={key: int(index) for key, index in value["vocabulary"].items()},
            idf={key: float(score) for key, score in value["idf"].items()},
            average_document_length=float(value["average_document_length"]),
            k1=float(value.get("k1", 1.5)),
            b=float(value.get("b", 0.75)),
        )
