import httpx
import pytest

from support_agent.retrieval import (BM25Retriever, HashEmbedder, OpenAIEmbedder, QdrantRetriever,
                                     make_retriever, tokenize)


@pytest.fixture(scope="module")
def bm25():
    return BM25Retriever()


@pytest.fixture(scope="module")
def qdrant():
    return QdrantRetriever(HashEmbedder())


def test_tokenize_drops_stop_words_and_stems():
    assert tokenize("How do I restart my servers?") == ["restart", "server"]


@pytest.mark.parametrize("query, article", [
    ("how do I restart my server", "restart-server"),
    ("I deleted my world by accident, can I get it back", "backups"),
    ("filezilla connection refused", "sftp-access"),
    ("server crashes on startup with a java error", "server-wont-start"),
    ("players get lag spikes, tps is low", "server-lag"),
])
def test_bm25_finds_the_right_article(bm25, query, article):
    assert bm25.search(query, k=3)[0].article_id == article


def test_scores_are_normalised_and_one_hit_per_article(bm25):
    hits = bm25.search("restart server", k=5)
    assert all(0 < h.score <= 1 for h in hits)
    assert len({h.article_id for h in hits}) == len(hits)


def test_off_topic_query_scores_low(bm25):
    on = bm25.search("how do I restart my server")[0].score
    off = bm25.search("what is your opinion about the football final yesterday evening")
    assert not off or off[0].score < on / 3


def test_empty_query_returns_nothing(bm25, qdrant):
    assert bm25.search("   ") == [] and qdrant.search("the and of") == []


def test_qdrant_backend_ranks_the_obvious_match_first(qdrant):
    hit = qdrant.search("restart reboot server frozen", k=3)[0]
    assert hit.article_id == "restart-server" and 0 < hit.score <= 1


def test_hash_embedder_is_deterministic_and_unit_length():
    a, b = HashEmbedder()(["open a port"]), HashEmbedder()(["open a port"])
    assert a == b and abs(sum(v * v for v in a[0]) - 1) < 1e-9


def test_openai_embedder_parses_response_in_index_order():
    def handler(request):
        return httpx.Response(200, json={"data": [{"index": 1, "embedding": [0.0, 1.0]},
                                                  {"index": 0, "embedding": [1.0, 0.0]}]})
    emb = OpenAIEmbedder(url="https://x/v1", key="k", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert emb(["a", "b"]) == [[1.0, 0.0], [0.0, 1.0]]


def test_make_retriever_rejects_unknown_names():
    with pytest.raises(ValueError, match="bm25, qdrant"):
        make_retriever("elastic")
