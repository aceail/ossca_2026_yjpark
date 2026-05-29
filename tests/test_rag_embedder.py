from rag.embedder import embed_text, embed_batch, EmbedderError


def _fake_call(payload):
    # Ollama /api/embeddings response shape: {"embedding": [...]}
    n = len(payload.get("input", payload.get("prompt", "x")))
    return {"embedding": [float(i) / max(n, 1) for i in range(768)]}


def test_embed_text_returns_768_floats():
    v = embed_text("hello world", _call=_fake_call)
    assert len(v) == 768
    assert all(isinstance(x, float) for x in v)


def test_embed_text_strips_and_rejects_empty():
    import pytest
    with pytest.raises(EmbedderError):
        embed_text("   ", _call=_fake_call)


def test_embed_batch_preserves_order():
    out = embed_batch(["a", "bb", "ccc"], _call=_fake_call)
    assert len(out) == 3
    assert all(len(v) == 768 for v in out)
