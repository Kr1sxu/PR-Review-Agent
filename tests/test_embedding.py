"""
Embedding Client Tests
Based on AgentScope EmbeddingModelBase
"""

import pytest
from agentscope.credential._openai import OpenAICredential
from src.models.embedding import MiMoEmbeddingModel, create_embedding_model


class TestEmbeddingOffline:
    """Offline mode tests"""

    def test_offline_when_no_config(self):
        credential = OpenAICredential(api_key="", base_url="")
        model = MiMoEmbeddingModel(credential=credential, dimensions=128)
        assert model.offline is True

    def test_online_mode(self):
        credential = OpenAICredential(api_key="sk-test", base_url="https://api.test.com")
        model = MiMoEmbeddingModel(credential=credential, dimensions=128)
        assert model.offline is False

    def test_offline_single_returns_zeros(self):
        credential = OpenAICredential(api_key="", base_url="")
        model = MiMoEmbeddingModel(credential=credential, dimensions=128)
        vec = model.embed_single("test text")
        assert len(vec) == 128
        assert all(v == 0.0 for v in vec)

    def test_offline_batch_returns_zeros(self):
        credential = OpenAICredential(api_key="", base_url="")
        model = MiMoEmbeddingModel(credential=credential, dimensions=64)
        texts = ["text1", "text2", "text3"]
        vecs = model.embed_batch(texts)
        assert len(vecs) == 3
        for vec in vecs:
            assert len(vec) == 64
            assert all(v == 0.0 for v in vec)

    def test_empty_input(self):
        credential = OpenAICredential(api_key="", base_url="")
        model = MiMoEmbeddingModel(credential=credential, dimensions=64)
        assert model.embed_batch([]) == []

    def test_empty_text_returns_zeros(self):
        credential = OpenAICredential(api_key="", base_url="")
        model = MiMoEmbeddingModel(credential=credential, dimensions=32)
        vec = model.embed_single("   ")
        assert len(vec) == 32
        assert all(v == 0.0 for v in vec)


class TestSimilarity:
    """Similarity tests"""

    def test_identical_vectors(self):
        vec = [1.0, 2.0, 3.0]
        assert MiMoEmbeddingModel.similarity(vec, vec) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert MiMoEmbeddingModel.similarity([1, 0], [0, 1]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        assert MiMoEmbeddingModel.similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)

    def test_empty_vectors(self):
        assert MiMoEmbeddingModel.similarity([], []) == 0.0

    def test_zero_vector(self):
        assert MiMoEmbeddingModel.similarity([0, 0, 0], [1, 2, 3]) == 0.0

    def test_dimension_mismatch(self):
        assert MiMoEmbeddingModel.similarity([1, 2], [1, 2, 3]) == 0.0


class TestEmbeddingConfig:
    """Configuration tests"""

    def test_custom_dimensions(self):
        credential = OpenAICredential(api_key="sk-test", base_url="https://api.test.com")
        model = MiMoEmbeddingModel(credential=credential, dimensions=512)
        assert model.dimensions == 512

    def test_factory_function(self):
        model = create_embedding_model(
            api_url="https://api.test.com",
            api_key="sk-test",
            dimensions=256,
        )
        assert isinstance(model, MiMoEmbeddingModel)
        assert model.dimensions == 256
        assert model.offline is False

    def test_factory_offline(self):
        model = create_embedding_model(api_url="", api_key="")
        assert model.offline is True
