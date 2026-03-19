import pytest

from askflow.embedding.chunker import chunk_text


class TestChunkText:
    def test_basic_chunking(self):
        text = "Paragraph one content.\n\nParagraph two content.\n\nParagraph three content."
        chunks = chunk_text(text, chunk_size=50, chunk_overlap=10)
        assert len(chunks) >= 1
        assert all(isinstance(c, str) for c in chunks)

    def test_empty_text(self):
        assert chunk_text("") == []

    def test_single_paragraph(self):
        text = "This is a single paragraph."
        chunks = chunk_text(text, chunk_size=1000)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_respects_chunk_size(self):
        text = "\n\n".join(f"Paragraph {i} with some content here." for i in range(20))
        chunks = chunk_text(text, chunk_size=100, chunk_overlap=10)
        assert len(chunks) > 1

    def test_whitespace_only(self):
        assert chunk_text("   \n\n   \n\n   ") == []
