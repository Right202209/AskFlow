from __future__ import annotations

import re


def chunk_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[str]:
    paragraphs = _split_paragraphs(text)
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_length = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        para_len = len(para)
        if current_length + para_len > chunk_size and current_chunk:
            chunks.append("\n".join(current_chunk))
            overlap_text = "\n".join(current_chunk)
            overlap_start = max(0, len(overlap_text) - chunk_overlap)
            carry_over = overlap_text[overlap_start:]
            current_chunk = [carry_over] if carry_over.strip() else []
            current_length = len(carry_over) if carry_over.strip() else 0
        current_chunk.append(para)
        current_length += para_len

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return [c for c in chunks if c.strip()]


def _split_paragraphs(text: str) -> list[str]:
    return re.split(r"\n{2,}", text)
