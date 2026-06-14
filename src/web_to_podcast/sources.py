from __future__ import annotations

import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import deque
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .config import PipelineConfig
from .document import SourceDocument


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.links.append(value)


def collect_sources(config: PipelineConfig) -> list[SourceDocument]:
    """Load configured web and local sources into source documents."""
    docs: list[SourceDocument] = []
    seen: set[str] = set()

    for item in _configured_url_items(config):
        doc = _load_url_item(item, config)
        if _dedupe_key(doc) not in seen:
            docs.append(doc)
            seen.add(_dedupe_key(doc))

    for item in _sitemap_url_items(config):
        doc = _load_url_item(item, config)
        if _dedupe_key(doc) not in seen:
            docs.append(doc)
            seen.add(_dedupe_key(doc))

    for item in _crawl_url_items(config):
        doc = _load_url_item(item, config)
        if _dedupe_key(doc) not in seen:
            docs.append(doc)
            seen.add(_dedupe_key(doc))

    for item in config.source.local_files:
        doc = _load_local_item(item, config)
        if _dedupe_key(doc) not in seen:
            docs.append(doc)
            seen.add(_dedupe_key(doc))

    return sorted(docs, key=lambda doc: (doc.section, doc.order if doc.order is not None else 999999, doc.title))


def fetch_url(url: str, *, timeout: int = 30, user_agent: str = "web-to-podcast/0.1") -> tuple[str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        content_type = response.headers.get("content-type", "")
        charset = response.headers.get_content_charset() or "utf-8"
        body = response.read()
    return body.decode(charset, errors="replace"), content_type


def fetch_url_with_renderer(url: str, config: PipelineConfig) -> tuple[str, str]:
    """Fetch a URL with the configured renderer.

    `static` uses urllib. `playwright` renders JavaScript pages. `auto` tries
    Playwright first and falls back to static fetching if browser dependencies
    are not installed or rendering fails.
    """
    renderer = (config.source.renderer or "static").lower()
    if renderer == "static":
        return fetch_url(url, timeout=config.source.timeout_seconds, user_agent=config.source.user_agent)
    if renderer in {"playwright", "browser", "auto"}:
        try:
            return _fetch_url_playwright(url, config), "text/html; rendered=playwright"
        except Exception:
            if renderer == "auto":
                return fetch_url(url, timeout=config.source.timeout_seconds, user_agent=config.source.user_agent)
            raise
    raise ValueError(f"unsupported source renderer: {config.source.renderer}")


def _configured_url_items(config: PipelineConfig) -> list[dict[str, Any]]:
    items = [_normalize_item(item, default_key="url") for item in config.source.urls]
    if config.source.url_file:
        path = _resolve_path(config.source.url_file, config)
        for line in path.read_text(encoding="utf-8").splitlines():
            clean = line.strip()
            if clean and not clean.startswith("#"):
                items.append({"url": clean})
    return items


def _sitemap_url_items(config: PipelineConfig) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    order = 1
    for sitemap_url in config.source.sitemap_urls:
        xml_text, _ = fetch_url(
            sitemap_url,
            timeout=config.source.timeout_seconds,
            user_agent=config.source.user_agent,
        )
        for url in _parse_sitemap_locations(xml_text):
            if _url_allowed(url, [], []):
                items.append({"url": url, "order": order})
                order += 1
    return items


def _crawl_url_items(config: PipelineConfig) -> list[dict[str, Any]]:
    crawl = config.source.crawl
    if not crawl.start_urls or crawl.max_pages <= 0:
        return []

    queue: deque[str] = deque(crawl.start_urls)
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    root_hosts = {urllib.parse.urlparse(url).netloc for url in crawl.start_urls}

    while queue and len(items) < crawl.max_pages:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        if crawl.same_domain and urllib.parse.urlparse(url).netloc not in root_hosts:
            continue
        if not _url_allowed(url, crawl.include_patterns, crawl.exclude_patterns):
            continue
        try:
            html_text, content_type = fetch_url_with_renderer(url, config)
        except Exception:
            continue
        items.append({"url": url, "order": len(items) + 1, "_prefetched": html_text, "_content_type": content_type})
        if "html" not in content_type.lower() and "<a " not in html_text.lower():
            continue
        for link in _extract_links(url, html_text):
            if link not in seen:
                queue.append(link)
    return items


def _load_url_item(item: dict[str, Any], config: PipelineConfig) -> SourceDocument:
    url = str(item.get("url") or "").strip()
    if not url:
        raise ValueError("URL source item is missing url")
    raw = str(item.get("_prefetched") or "")
    content_type = str(item.get("_content_type") or "")
    if not raw:
        raw, content_type = fetch_url_with_renderer(url, config)
    return SourceDocument.build(
        raw_text=raw,
        title=str(item.get("title") or ""),
        source_url=url,
        section=str(item.get("section") or ""),
        order=_optional_int(item.get("order")),
        media_type=content_type or "text/html",
        metadata={key: value for key, value in item.items() if not str(key).startswith("_")},
    )


def _load_local_item(item: Any, config: PipelineConfig) -> SourceDocument:
    data = _normalize_item(item, default_key="path")
    path = _resolve_path(str(data.get("path") or ""), config)
    if not path.exists():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        media_type = "text/markdown"
    elif suffix in {".html", ".htm"}:
        media_type = "text/html"
    elif suffix in {".txt"}:
        media_type = "text/plain"
    else:
        raise ValueError(f"unsupported local file type: {path.suffix}. Convert it to Markdown/Text first.")
    return SourceDocument.build(
        raw_text=path.read_text(encoding="utf-8", errors="replace"),
        title=str(data.get("title") or path.stem),
        source_path=str(path),
        section=str(data.get("section") or ""),
        order=_optional_int(data.get("order")),
        media_type=media_type,
        metadata={key: value for key, value in data.items() if key != "path"},
    )


def _normalize_item(item: Any, *, default_key: str) -> dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)
    return {default_key: str(item)}


def _resolve_path(value: str, config: PipelineConfig) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute() or path.exists():
        return path
    if config.config_path:
        candidate = config.config_path.parent / path
        if candidate.exists():
            return candidate
    return path


def _parse_sitemap_locations(xml_text: str) -> list[str]:
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError:
        return []
    locations: list[str] = []
    for elem in root.iter():
        if elem.tag.endswith("loc") and elem.text:
            locations.append(elem.text.strip())
    return locations


def _extract_links(base_url: str, html_text: str) -> list[str]:
    parser = _LinkParser()
    parser.feed(html_text)
    parser.close()
    links: list[str] = []
    for href in parser.links:
        absolute = urllib.parse.urljoin(base_url, href)
        parsed = urllib.parse.urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        links.append(urllib.parse.urlunparse(parsed._replace(fragment="")))
    return links


def _fetch_url_playwright(url: str, config: PipelineConfig) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright renderer requested. Install with: pip install -e '.[browser]' && python -m playwright install chromium") from exc

    timeout_ms = max(1, int(config.source.timeout_seconds)) * 1000
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(user_agent=config.source.user_agent)
        page = context.new_page()
        try:
            page.goto(url, wait_until=config.source.wait_until, timeout=timeout_ms)
            _scroll_page(page, config.source.max_scrolls)
            for selector in config.source.remove_selectors:
                page.locator(selector).evaluate_all("(els) => els.forEach((el) => el.remove())")
            title = ""
            if config.source.title_selector:
                locator = page.locator(config.source.title_selector).first
                if locator.count():
                    title = locator.inner_text(timeout=timeout_ms).strip()
            if not title:
                title = page.title().strip()
            if config.source.content_selector:
                locator = page.locator(config.source.content_selector).first
                if locator.count():
                    body = locator.evaluate("(el) => el.outerHTML", timeout=timeout_ms)
                else:
                    body = page.content()
            else:
                body = page.content()
            if title and "<h1" not in body.lower():
                body = f"<article><h1>{title}</h1>\n{body}</article>"
            return body
        finally:
            context.close()
            browser.close()


def _scroll_page(page: Any, max_scrolls: int) -> None:
    for _ in range(max(0, int(max_scrolls))):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(0.4)


def _url_allowed(url: str, include_patterns: list[str], exclude_patterns: list[str]) -> bool:
    if include_patterns and not any(re.search(pattern, url) for pattern in include_patterns):
        return False
    if exclude_patterns and any(re.search(pattern, url) for pattern in exclude_patterns):
        return False
    return True


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _dedupe_key(doc: SourceDocument) -> str:
    return doc.source_url or doc.source_path or doc.id
