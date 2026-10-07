"""Retrieval over knowledge-base chunks. Two interchangeable backends:

- BM25Retriever: pure Python, no dependencies, the default.
- QdrantRetriever: vectors in Qdrant (in-memory or a server) from a pluggable embedder:
  HashEmbedder (deterministic, offline) or OpenAIEmbedder (any OpenAI-compatible endpoint).

Scores are normalised to 0..1 so one handoff threshold works for both.
"""
import hashlib
import math
import os
import re
from collections import Counter
from typing import Protocol

import httpx

from .kb import chunks as make_chunks, load_articles
from .models import Chunk, Hit

STOP = set("""a an the and or of to in on for with is are be was were it this that my our your i you we
can how do does what why when where which please help need get have has from at by as me not
hi hello hey dear thanks thank team guys hope great love loyal customer years today yesterday evening
morning since about all also just really very been being would could should will im ive id there here
some any but so if then than its after before still again now got everything anything something
everyone friends few two months weeks days ago lot much many doing re ll ve service
""".split())  # includes the pleasantries customers wrap a question in, so they do not dilute the score


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-zа-яіїєґ0-9]+", text.lower())
    out = []
    for t in tokens:
        if t in STOP or len(t) < 2:
            continue
        out.append(stem(t))
    return out


def stem(token: str) -> str:
    """Tiny suffix stripper: mods/mod, changed/change, files/file, updates/update meet."""
    for suffix in ("ing", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            token = token[: -len(suffix)]
            break
    if token.endswith("e") and len(token) > 4:
        token = token[:-1]
    return token


class Retriever(Protocol):
    name: str
    def search(self, query: str, k: int = 3) -> list[Hit]: ...


def best_per_article(hits: list[Hit]) -> list[Hit]:
    seen, out = set(), []
    for h in sorted(hits, key=lambda h: -h.score):
        if h.article_id not in seen:
            seen.add(h.article_id)
            out.append(h)
    return out


UNKNOWN_WEIGHT = 0.75  # picked with the eval sweep: 1.0 drowns long tickets, 0.5 lets off-topic ones through


class BM25Retriever:
    name = "bm25"

    def __init__(self, chunks: list[Chunk] | None = None, k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks if chunks is not None else make_chunks(load_articles())
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(c.text)) for c in self.chunks]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.lengths) / len(self.lengths) if self.lengths else 0
        n = len(self.docs)
        df = Counter(t for d in self.docs for t in d)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.max_idf = math.log(1 + (n + 0.5) / 0.5)  # idf of a term no chunk contains

    def _raw(self, terms: list[str], i: int) -> float:
        doc, length, score = self.docs[i], self.lengths[i], 0.0
        for t in terms:
            tf = doc.get(t, 0)
            if tf:
                denom = tf + self.k1 * (1 - self.b + self.b * length / self.avg)
                score += self.idf[t] * tf * (self.k1 + 1) / denom
        return score

    def search(self, query: str, k: int = 3) -> list[Hit]:
        terms = tokenize(query)
        if not terms or not self.docs:
            return []
        # upper bound for this query: every known term matched with saturated tf. Words the KB has
        # never seen count at reduced weight: enough that a question mostly about something else
        # scores low, not so much that a long, chatty ticket drowns its one real question
        ceiling = sum((self.idf[t] if t in self.idf else UNKNOWN_WEIGHT * self.max_idf) * (self.k1 + 1)
                      for t in terms)
        scored = [(self._raw(terms, i) / ceiling, i) for i in range(len(self.docs))]
        scored = sorted((s for s in scored if s[0] > 0), reverse=True)[: max(k * 3, k)]
        hits = [Hit(c.article_id, c.chunk_id, c.title, c.text, round(s, 4))
                for s, i in scored for c in [self.chunks[i]]]
        return best_per_article(hits)[:k]


class HashEmbedder:
    """Feature hashing of words and word pairs. Deterministic and offline: good enough to
    exercise the Qdrant path in tests and demos, not a substitute for a real model."""

    def __init__(self, dim: int = 512):
        self.dim = dim

    def __call__(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        toks = tokenize(text)
        for feature in toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]:
            h = int(hashlib.md5(feature.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0 if (h >> 64) & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class OpenAIEmbedder:
    """Any OpenAI-compatible /embeddings endpoint (SA_EMBED_URL, SA_EMBED_KEY, SA_EMBED_MODEL)."""

    def __init__(self, url: str | None = None, key: str | None = None, model: str | None = None,
                 client: httpx.Client | None = None):
        self.url = (url or os.environ.get("SA_EMBED_URL", "https://api.openai.com/v1")).rstrip("/")
        self.key = key or os.environ.get("SA_EMBED_KEY", "")
        self.model = model or os.environ.get("SA_EMBED_MODEL", "text-embedding-3-small")
        self.client = client

    def __call__(self, texts: list[str]) -> list[list[float]]:
        body = {"model": self.model, "input": texts}
        headers = {"Authorization": f"Bearer {self.key}"}
        if self.client is not None:
            response = self.client.post(f"{self.url}/embeddings", json=body, headers=headers)
        else:
            with httpx.Client(timeout=30) as http:
                response = http.post(f"{self.url}/embeddings", json=body, headers=headers)
        response.raise_for_status()
        data = sorted(response.json()["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in data]


class QdrantRetriever:
    name = "qdrant"

    def __init__(self, embedder=None, chunks: list[Chunk] | None = None, location: str | None = None,
                 prefix: str = "kb"):
        try:
            from qdrant_client import QdrantClient, models
        except ImportError as exc:  # optional dependency
            raise RuntimeError('the qdrant retriever needs: pip install "support-agent[qdrant]"') from exc

        self.embedder = embedder or HashEmbedder()
        self.chunks = chunks if chunks is not None else make_chunks(load_articles())
        # the collection name carries a hash of the KB and the embedder, so a server collection is
        # reused when nothing changed and never dropped under another worker
        fingerprint = hashlib.sha256((repr(self.embedder.__class__.__name__) + getattr(self.embedder, "model", "")
                                      + "".join(c.chunk_id + c.text for c in self.chunks)).encode()).hexdigest()[:12]
        self.collection = f"{prefix}_{fingerprint}"
        url = location or os.environ.get("SA_QDRANT_URL")
        self.client = QdrantClient(url=url) if url else QdrantClient(":memory:")
        if self.client.collection_exists(self.collection):
            return
        vectors = self.embedder([c.text for c in self.chunks])
        self.client.create_collection(self.collection, vectors_config=models.VectorParams(
            size=len(vectors[0]), distance=models.Distance.COSINE))
        self.client.upsert(self.collection, points=[
            models.PointStruct(id=i, vector=v, payload={"article_id": c.article_id, "chunk_id": c.chunk_id,
                                                          "title": c.title, "text": c.text})
            for i, (c, v) in enumerate(zip(self.chunks, vectors))])

    def search(self, query: str, k: int = 3) -> list[Hit]:
        if not tokenize(query):
            return []
        vector = self.embedder([query])[0]
        result = self.client.query_points(self.collection, query=vector, limit=k * 3, with_payload=True)
        hits = [Hit(p.payload["article_id"], p.payload["chunk_id"], p.payload["title"], p.payload["text"],
                    round(max(0.0, p.score), 4)) for p in result.points]
        return best_per_article(hits)[:k]


def make_retriever(name: str | None = None) -> Retriever:
    name = name or os.environ.get("SA_RETRIEVER", "bm25")
    if name == "bm25":
        return BM25Retriever()
    if name == "qdrant":
        embedder = OpenAIEmbedder() if os.environ.get("SA_EMBED_KEY") else HashEmbedder()
        return QdrantRetriever(embedder)
    raise ValueError(f"unknown retriever '{name}'. Valid: bm25, qdrant")
