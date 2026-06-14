from __future__ import annotations

import html
import re
from html.parser import HTMLParser

from .document import SourceDocument


class _ReadableHTMLParser(HTMLParser):
    block_tags = {
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }
    skip_tags = {"script", "style", "svg", "noscript", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._in_h1 = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.skip_tags:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        if tag == "h1":
            self._in_h1 = True
        if tag in self.block_tags:
            self._newline()
        if tag == "li":
            self.parts.append("- ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.skip_tags and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag == "title":
            self._in_title = False
        if tag == "h1":
            self._in_h1 = False
        if tag in self.block_tags:
            self._newline()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = html.unescape(data)
        if not text.strip():
            return
        if self._in_title:
            self.title_parts.append(text)
            return
        if self._in_h1:
            self.h1_parts.append(text)
        self.parts.append(text)

    def _newline(self) -> None:
        if self.parts and not str(self.parts[-1]).endswith("\n"):
            self.parts.append("\n")

    @property
    def text(self) -> str:
        return _collapse_text("".join(self.parts))

    @property
    def title(self) -> str:
        h1 = _collapse_inline(" ".join(self.h1_parts))
        title = _collapse_inline(" ".join(self.title_parts))
        return h1 or title


def extract_readable_text(document: SourceDocument, *, extractor: str = "basic") -> tuple[str, str]:
    """Return `(title, text)` for a source document."""
    media_type = (document.media_type or "").lower()
    raw = document.raw_text or ""
    if "html" in media_type or _looks_like_html(raw):
        extracted = _extract_html_with_backend(raw, extractor)
        if extracted:
            extracted_title, extracted_text = extracted
            title = document.title if document.title and document.title != "Untitled" else extracted_title
            return title or document.title or "Untitled", extracted_text
        parser = _ReadableHTMLParser()
        parser.feed(raw)
        parser.close()
        title = document.title if document.title and document.title != "Untitled" else parser.title
        return title or document.title or "Untitled", parser.text
    return document.title, clean_source_text(raw)


def _extract_html_with_backend(raw: str, extractor: str) -> tuple[str, str] | None:
    backend = (extractor or "basic").strip().lower()
    if backend == "basic":
        return None
    if backend not in {"auto", "trafilatura"}:
        raise ValueError("source.extractor must be one of: basic, auto, trafilatura")
    try:
        import trafilatura
    except ImportError as exc:
        if backend == "auto":
            return None
        raise RuntimeError("trafilatura extractor requested. Install with: pip install -e '.[extract]'") from exc

    text = trafilatura.extract(
        raw,
        output_format="txt",
        include_comments=False,
        include_tables=True,
        favor_precision=False,
    )
    if not text or not text.strip():
        return None
    title = ""
    try:
        metadata = trafilatura.extract_metadata(raw)
        title = str(getattr(metadata, "title", "") or "").strip()
    except Exception:
        title = ""
    return title, _collapse_text(text)


def clean_source_text(raw_text: str) -> str:
    """Convert common Markdown or text source into readable prose."""
    text = _normalize_text(raw_text)
    text = re.sub(r"```.*?```", "\n", text, flags=re.DOTALL)
    text = re.sub(r"(?m)^(?: {4}|\t).*$", "", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "\n", text)
    text = re.sub(r"(?m)^\s*[-*+]\s+", "", text)
    text = re.sub(r"(?m)^\s*\d+[.)]\s+", "", text)
    text = re.sub(r"(?m)^\s*>\s?", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"[*_~]{1,3}([^*_~]+)[*_~]{1,3}", r"\1", text)
    return _collapse_text(text)


def _looks_like_html(text: str) -> bool:
    head = text[:500].lower()
    return "<html" in head or "<body" in head or "</p>" in head or "<article" in head


def _normalize_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = text.replace("\u2013", "-").replace("\u2014", "--")
    return text


def _collapse_inline(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _collapse_text(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in (text or "").splitlines()]
    paragraphs: list[str] = []
    buffer: list[str] = []
    for line in lines:
        if not line:
            if buffer:
                paragraphs.append(" ".join(buffer).strip())
                buffer = []
            continue
        buffer.append(line)
    if buffer:
        paragraphs.append(" ".join(buffer).strip())
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)
