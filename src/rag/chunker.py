"""
Markdown Text Chunker - PR-Review Agent
Semantic chunking by Markdown headings/paragraphs
Configurable chunk_size and overlap, preserves metadata
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class Chunk:
    """A text chunk with metadata"""
    text: str
    source_file: str = ""
    section_title: str = ""
    chunk_index: int = 0
    metadata: dict = field(default_factory=dict)

    def to_context_text(self) -> str:
        """Format chunk for context injection"""
        prefix = f"[Source: {self.source_file}"
        if self.section_title:
            prefix += f", Section: {self.section_title}"
        prefix += "]"
        return f"{prefix}\n{self.text}"


class MarkdownChunker:
    """
    Markdown semantic chunker
    - Splits by headings (# ## ###) as primary boundaries
    - Further splits large sections by paragraphs
    - Configurable chunk_size (chars) and overlap
    - Preserves source file and section title metadata
    """

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_file(self, file_path: str) -> List[Chunk]:
        """
        Chunk a single Markdown file.
        :param file_path: Path to the Markdown file
        :return: List of Chunk objects
        """
        path = Path(file_path)
        if not path.exists():
            return []
        content = path.read_text(encoding="utf-8")
        return self.chunk_text(content, source_file=path.name)

    def chunk_text(self, text: str, source_file: str = "") -> List[Chunk]:
        """
        Chunk Markdown text semantically.
        :param text: Markdown text content
        :param source_file: Source file name for metadata
        :return: List of Chunk objects
        """
        sections = self._split_by_headings(text)
        chunks = []
        chunk_index = 0

        for section_title, section_text in sections:
            section_text = section_text.strip()
            if not section_text:
                continue

            # If section fits in one chunk, keep it whole
            if len(section_text) <= self.chunk_size:
                chunks.append(Chunk(
                    text=section_text,
                    source_file=source_file,
                    section_title=section_title,
                    chunk_index=chunk_index,
                ))
                chunk_index += 1
            else:
                # Split large sections by paragraphs
                sub_chunks = self._split_by_paragraphs(section_text)
                for sub_text in sub_chunks:
                    chunks.append(Chunk(
                        text=sub_text,
                        source_file=source_file,
                        section_title=section_title,
                        chunk_index=chunk_index,
                    ))
                    chunk_index += 1

        return chunks

    def _split_by_headings(self, text: str) -> List[tuple]:
        """
        Split Markdown by headings, returning (title, content) pairs.
        """
        lines = text.split("\n")
        sections = []
        current_title = ""
        current_lines = []

        for line in lines:
            heading_match = re.match(r"^(#{1,6})\s+(.+)", line)
            if heading_match:
                # Save previous section
                if current_lines:
                    sections.append((current_title, "\n".join(current_lines)))
                current_title = heading_match.group(2).strip()
                current_lines = [line]
            else:
                current_lines.append(line)

        # Save last section
        if current_lines:
            sections.append((current_title, "\n".join(current_lines)))

        return sections

    def _split_by_paragraphs(self, text: str) -> List[str]:
        """
        Split large text by paragraphs with overlap.
        """
        # Split by double newline (paragraph boundary)
        paragraphs = re.split(r"\n\n+", text)
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # If single paragraph exceeds chunk_size, force split by sentences
            if len(para) > self.chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                sentence_chunks = self._force_split(para)
                chunks.extend(sentence_chunks)
                continue

            # Try to accumulate paragraphs
            if len(current_chunk) + len(para) + 2 <= self.chunk_size:
                current_chunk = f"{current_chunk}\n\n{para}" if current_chunk else para
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                # Overlap: include last part of previous chunk
                if self.chunk_overlap > 0 and current_chunk:
                    overlap_text = current_chunk[-self.chunk_overlap:]
                    current_chunk = f"{overlap_text}\n\n{para}"
                else:
                    current_chunk = para

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks

    def _force_split(self, text: str) -> List[str]:
        """Force split text by character limit"""
        chunks = []
        for i in range(0, len(text), self.chunk_size - self.chunk_overlap):
            chunk = text[i:i + self.chunk_size]
            if chunk.strip():
                chunks.append(chunk.strip())
        return chunks
