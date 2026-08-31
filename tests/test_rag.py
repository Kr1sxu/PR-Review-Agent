"""
RAG Module Tests - PR-Review Agent
Test chunking, vector store, retrieval, degradation
"""

import pytest
from pathlib import Path

from src.rag.chunker import MarkdownChunker, Chunk
from src.rag.vector_store import VectorStore
from src.rag.retriever import RAGRetriever
from src.models.embedding import create_embedding_model


class TestMarkdownChunker:
    """Markdown chunker tests"""

    def test_chunk_by_heading(self):
        """Test splitting by Markdown headings"""
        text = """# Title

## Section A
Content of section A.

## Section B
Content of section B.
"""
        chunker = MarkdownChunker(chunk_size=200)
        chunks = chunker.chunk_text(text, source_file="test.md")
        assert len(chunks) >= 2
        titles = [c.section_title for c in chunks]
        assert "Section A" in titles
        assert "Section B" in titles

    def test_chunk_preserves_source(self):
        """Test metadata preservation"""
        text = """## Intro
Hello world."""
        chunker = MarkdownChunker()
        chunks = chunker.chunk_text(text, source_file="spec.md")
        assert chunks[0].source_file == "spec.md"
        assert chunks[0].section_title == "Intro"

    def test_chunk_large_section(self):
        """Test splitting large sections by paragraphs"""
        # Create text larger than chunk_size
        paragraphs = [f"Paragraph {i}. " * 20 for i in range(10)]
        text = "## Big Section\n\n" + "\n\n".join(paragraphs)
        chunker = MarkdownChunker(chunk_size=200, chunk_overlap=20)
        chunks = chunker.chunk_text(text)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.text) > 0

    def test_chunk_empty_text(self):
        """Test empty input"""
        chunker = MarkdownChunker()
        chunks = chunker.chunk_text("")
        assert chunks == []

    def test_chunk_file(self, tmp_path):
        """Test chunking a file"""
        md_file = tmp_path / "test.md"
        md_file.write_text("""# Doc
## Section
Content here.""", encoding="utf-8")
        chunker = MarkdownChunker()
        chunks = chunker.chunk_file(str(md_file))
        assert len(chunks) >= 1
        assert chunks[0].source_file == "test.md"

    def test_chunk_nonexistent_file(self):
        """Test nonexistent file returns empty"""
        chunker = MarkdownChunker()
        chunks = chunker.chunk_file("/nonexistent/file.md")
        assert chunks == []

    def test_to_context_text(self):
        """Test context text formatting"""
        chunk = Chunk(text="content", source_file="spec.md", section_title="Security")
        ctx = chunk.to_context_text()
        assert "spec.md" in ctx
        assert "Security" in ctx
        assert "content" in ctx


class TestVectorStore:
    """Vector store tests"""

    def test_add_and_search(self):
        """Test basic add and search"""
        store = VectorStore()
        c1 = Chunk(text="SQL injection prevention", source_file="sec.md")
        c2 = Chunk(text="Payment idempotency", source_file="pay.md")
        store.add_batch([c1, c2], [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        # Query similar to c1
        results = store.search([0.9, 0.1, 0.0], top_k=1)
        assert len(results) == 1
        assert results[0][0].text == "SQL injection prevention"

    def test_search_empty_store(self):
        """Test search on empty store"""
        store = VectorStore()
        results = store.search([1.0, 0.0], top_k=5)
        assert results == []

    def test_search_threshold(self):
        """Test similarity threshold filtering"""
        store = VectorStore()
        store.add_batch(
            [Chunk(text="a"), Chunk(text="b")],
            [[1.0, 0.0], [0.0, 1.0]],
        )
        # Query orthogonal to both, threshold high
        results = store.search([1.0, 0.0], top_k=5, threshold=0.99)
        assert len(results) == 1  # only exact match passes

    def test_save_and_load_cache(self, tmp_path):
        """Test cache persistence"""
        cache_path = str(tmp_path / "cache.json")
        store = VectorStore()
        chunk = Chunk(text="test content", source_file="a.md", section_title="Intro")
        store.add(chunk, [0.1, 0.2, 0.3])
        store.save_cache(cache_path)

        # Load into new store
        store2 = VectorStore()
        assert store2.load_cache(cache_path) is True
        assert store2.count == 1
        assert store2.is_built is True
        results = store2.search([0.1, 0.2, 0.3], top_k=1)
        assert len(results) == 1
        assert results[0][0].text == "test content"

    def test_load_nonexistent_cache(self):
        """Test loading nonexistent cache returns False"""
        store = VectorStore()
        assert store.load_cache("/nonexistent/cache.json") is False

    def test_clear(self):
        """Test clearing the store"""
        store = VectorStore()
        store.add(Chunk(text="a"), [1.0])
        assert store.count == 1
        store.clear()
        assert store.count == 0
        assert store.is_built is False


class TestRAGRetriever:
    """RAG retriever tests"""

    def test_offline_degradation(self, tmp_path):
        """Test graceful degradation in offline mode"""
        model = create_embedding_model(api_url="", api_key="")
        retriever = RAGRetriever(
            embedding_model=model,
            knowledge_base_path=str(tmp_path),
        )
        # Should fail to initialize (offline = zero vectors)
        assert retriever.initialize() is False
        # Retrieve should return empty gracefully
        results = retriever.retrieve("test query")
        assert results == []

    def test_missing_kb_path(self):
        """Test missing knowledge base path"""
        model = create_embedding_model(api_url="", api_key="")
        retriever = RAGRetriever(
            embedding_model=model,
            knowledge_base_path="/nonexistent/path",
        )
        assert retriever.initialize() is False

    def test_empty_kb_directory(self, tmp_path):
        """Test empty knowledge base directory"""
        model = create_embedding_model(api_url="", api_key="")
        retriever = RAGRetriever(
            embedding_model=model,
            knowledge_base_path=str(tmp_path),
        )
        assert retriever.initialize() is False

    def test_get_context_string_empty(self, tmp_path):
        """Test context string returns empty on failure"""
        model = create_embedding_model(api_url="", api_key="")
        retriever = RAGRetriever(
            embedding_model=model,
            knowledge_base_path=str(tmp_path),
        )
        ctx = retriever.get_context_string("test")
        assert ctx == ""
