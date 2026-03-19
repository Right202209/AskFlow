import pytest

from askflow.embedding.parser import _parse_html, _parse_markdown


class TestParser:
    def test_parse_markdown(self):
        content = b"# Hello\n\nThis is **bold** text."
        result = _parse_markdown(content)
        assert "Hello" in result
        assert "bold" in result

    def test_parse_html(self):
        content = b"<html><body><h1>Title</h1><script>alert(1)</script><p>Content</p></body></html>"
        result = _parse_html(content)
        assert "Title" in result
        assert "Content" in result
        assert "alert" not in result

    def test_parse_html_strips_style(self):
        content = b"<html><head><style>body{color:red}</style></head><body><p>Text</p></body></html>"
        result = _parse_html(content)
        assert "Text" in result
        assert "color" not in result
