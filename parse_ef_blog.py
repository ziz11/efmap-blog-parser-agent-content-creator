#!/usr/bin/env python3
"""Scrape ef-map blog posts into LLM-friendly files (JSONL/Markdown)."""

from __future__ import annotations

import argparse
import json
import random
import re
import ssl
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

BASE_URL = "https://ef-map.com"
BLOG_INDEX = f"{BASE_URL}/blog/"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
USER_AGENT = "ef-map-blog-parser/1.0"


@dataclass
class Article:
    url: str
    slug: str
    title: str
    date_published: str | None
    description: str | None
    category: str | None
    content: str


def fetch(url: str, timeout: int = 20, insecure: bool = False) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    context = None
    if insecure:
        context = ssl._create_unverified_context()
    with urlopen(req, timeout=timeout, context=context) as resp:
        raw = resp.read()
        # Some pages send incorrect charset headers; prefer UTF-8 first.
        for charset in ("utf-8", resp.headers.get_content_charset(), "latin-1"):
            if not charset:
                continue
            try:
                return raw.decode(charset)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")


def fetch_with_retry(
    url: str,
    timeout: int = 20,
    insecure: bool = False,
    retries: int = 3,
    backoff: float = 1.5,
) -> str:
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return fetch(url, timeout=timeout, insecure=insecure)
        except Exception as exc:
            last_exc = exc
            permanent = isinstance(exc, HTTPError) and 400 <= exc.code < 500 and exc.code not in (408, 429)
            if permanent or attempt >= retries:
                break
            sleep_for = (backoff ** (attempt - 1)) + random.uniform(0.0, 0.35)
            time.sleep(sleep_for)
    raise RuntimeError(f"failed to fetch {url}: {last_exc}") from last_exc


def normalize_blog_url(link: str) -> str | None:
    """Canonicalize a blog article URL; return None for non-article links."""
    parsed = urlparse(urljoin(BASE_URL, link.strip()))
    if parsed.netloc not in ("ef-map.com", "www.ef-map.com"):
        return None
    path = parsed.path.rstrip("/")
    if not path.startswith("/blog/") or path == "/blog":
        return None
    return f"{BASE_URL}{path}"


def compact_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", fix_mojibake(text)).strip()


def fix_mojibake(text: str) -> str:
    # Common UTF-8 mojibake pattern rendered as latin-1 (e.g. â€” instead of —).
    if "â" not in text and "Ã" not in text:
        return text
    for src in ("cp1252", "latin-1"):
        try:
            repaired = text.encode(src).decode("utf-8")
            return repaired
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return text


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr_map = dict(attrs)
        href = attr_map.get("href")
        if not href:
            return
        link = normalize_blog_url(href)
        if link:
            self.links.add(link)


class MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_h1 = False
        self.capture_time = False
        self.capture_category = False
        self.title_parts: list[str] = []
        self.date: str | None = None
        self.category_parts: list[str] = []
        self.meta_description: str | None = None
        self.jsonld_scripts: list[str] = []
        self.in_jsonld = False
        self._jsonld_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        cls = attr_map.get("class") or ""

        if tag == "meta" and (attr_map.get("name") == "description"):
            raw = attr_map.get("content")
            self.meta_description = fix_mojibake(raw) if raw else raw

        if tag == "h1":
            self.in_h1 = True

        if tag == "time":
            self.capture_time = True
            if attr_map.get("datetime"):
                self.date = attr_map["datetime"]

        if tag in ("span", "div") and "category" in cls.split():
            self.capture_category = True

        if tag == "script" and (attr_map.get("type") or "").lower() == "application/ld+json":
            self.in_jsonld = True
            self._jsonld_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1":
            self.in_h1 = False
        if tag == "time":
            self.capture_time = False
        if tag in ("span", "div"):
            self.capture_category = False
        if tag == "script" and self.in_jsonld:
            script_text = "".join(self._jsonld_parts).strip()
            if script_text:
                self.jsonld_scripts.append(script_text)
            self.in_jsonld = False
            self._jsonld_parts = []

    def handle_data(self, data: str) -> None:
        text = compact_spaces(data)
        if not text:
            return
        if self.in_h1:
            self.title_parts.append(text)
        if self.capture_time and not self.date:
            self.date = text
        if self.capture_category:
            self.category_parts.append(text)
        if self.in_jsonld:
            self._jsonld_parts.append(data)

    @property
    def title(self) -> str:
        return compact_spaces(" ".join(self.title_parts))

    @property
    def category(self) -> str | None:
        raw = compact_spaces(" ".join(self.category_parts))
        return raw or None


class ArticleContentParser(HTMLParser):
    HEADINGS = {"h2": "## ", "h3": "### ", "h4": "#### ", "h5": "##### ", "h6": "###### "}
    # Tags that start a new text block; text buffered so far is flushed first.
    BLOCK_TAGS = {
        "p", "li", "blockquote", "div", "section", "figure", "figcaption",
        "ul", "ol", "dl", "dt", "dd", "pre", "table", "tr", "td", "th", *HEADINGS,
    }

    def __init__(self, base_url: str = BASE_URL) -> None:
        super().__init__()
        self.base_url = base_url
        self.article_depth = 0
        self.lines: list[str] = []
        self.parts: list[str] = []
        self.kinds: list[str] = []  # stack of open block tags inside the article
        self.list_depth = 0
        self.pre_depth = 0
        self.link_stack: list[str | None] = []
        self.table_rows: list[list[str]] | None = None
        self.row: list[str] | None = None

    @property
    def in_article(self) -> bool:
        return self.article_depth > 0

    def _current_kind(self) -> str:
        for kind in reversed(self.kinds):
            if kind not in ("div", "section", "figure", "ul", "ol", "dl", "table", "tr"):
                return kind
        return "p"

    def _flush(self) -> None:
        raw = "".join(self.parts)
        self.parts = []
        if self.pre_depth:
            text = raw.strip("\n")
            if text.strip():
                self.lines.append(f"```\n{fix_mojibake(text)}\n```")
            return
        text = compact_spaces(raw)
        if not text:
            return
        kind = self._current_kind()
        if self.row is not None and kind in ("td", "th"):
            self.row.append(text.replace("|", "\\|"))
        elif kind in self.HEADINGS:
            self.lines.append(f"{self.HEADINGS[kind]}{text}")
        elif kind == "li":
            indent = "  " * max(0, self.list_depth - 1)
            self.lines.append(f"{indent}- {text}")
        elif kind == "blockquote":
            self.lines.append(f"> {text}")
        else:
            self.lines.append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "article":
            if self.in_article or "content" in (attr_map.get("class") or "").split():
                self.article_depth += 1
            return
        if not self.in_article:
            return

        if tag in self.BLOCK_TAGS:
            self._flush()
            self.kinds.append(tag)
            if tag in ("ul", "ol"):
                self.list_depth += 1
            elif tag == "pre":
                self.pre_depth += 1
            elif tag == "table":
                self.table_rows = []
            elif tag == "tr" and self.table_rows is not None:
                self.row = []
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "a":
            self.link_stack.append(self._resolve_link(attr_map.get("href")))

    def handle_endtag(self, tag: str) -> None:
        if not self.in_article:
            return
        if tag == "article":
            self._flush()
            self.article_depth -= 1
            return

        if tag == "a" and self.link_stack:
            link = self.link_stack.pop()
            if link and "".join(self.parts).strip():
                self.parts.append(f" ({link})")
            return

        if tag not in self.BLOCK_TAGS or tag not in self.kinds:
            return
        self._flush()
        # Pop up to and including the matching tag (tolerates unclosed children).
        while self.kinds:
            closed = self.kinds.pop()
            if closed in ("ul", "ol") and self.list_depth > 0:
                self.list_depth -= 1
            elif closed == "pre" and self.pre_depth > 0:
                self.pre_depth -= 1
            elif closed == "tr" and self.row is not None:
                self._emit_row()
            elif closed == "table" and self.table_rows is not None:
                self._emit_table()
            if closed == tag:
                break

    def _emit_row(self) -> None:
        row, self.row = self.row, None
        if row and self.table_rows is not None:
            self.table_rows.append(row)

    def _emit_table(self) -> None:
        rows, self.table_rows = self.table_rows, None
        if not rows:
            return
        width = max(len(r) for r in rows)
        out = []
        for idx, r in enumerate(rows):
            r = r + [""] * (width - len(r))
            out.append("| " + " | ".join(r) + " |")
            if idx == 0:
                out.append("|" + " --- |" * width)
        self.lines.append("\n".join(out))

    def _resolve_link(self, href: str | None) -> str | None:
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            return None
        link = urljoin(self.base_url, href)
        return link if urlparse(link).scheme in ("http", "https") else None

    def handle_data(self, data: str) -> None:
        if self.in_article:
            # convert_charrefs=True (default) already unescapes entities.
            self.parts.append(data)

    def get_content(self) -> str:
        return "\n\n".join(line.strip("\n") for line in self.lines if line.strip()).strip()


def discover_from_sitemap(xml_text: str) -> set[str]:
    urls: set[str] = set()
    root = ET.fromstring(xml_text)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    for loc in root.findall("sm:url/sm:loc", ns):
        if not loc.text:
            continue
        link = normalize_blog_url(loc.text)
        if link:
            urls.add(link)
    return urls


def discover_from_index(index_html: str) -> set[str]:
    parser = LinkCollector()
    parser.feed(index_html)
    return parser.links


def parse_article(url: str, html: str) -> Article:
    meta = MetadataParser()
    meta.feed(html)

    body = ArticleContentParser(base_url=url)
    body.feed(html)

    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    title = meta.title or slug.replace("-", " ").title()
    date_published = meta.date
    if not date_published:
        for blob in meta.jsonld_scripts:
            try:
                obj = json.loads(blob)
            except json.JSONDecodeError:
                continue
            candidates = obj if isinstance(obj, list) else [obj]
            if isinstance(obj, dict) and isinstance(obj.get("@graph"), list):
                candidates = candidates + obj["@graph"]
            for item in candidates:
                if isinstance(item, dict) and item.get("datePublished"):
                    date_published = str(item["datePublished"])
                    break
            if date_published:
                break

    return Article(
        url=url,
        slug=slug,
        title=title,
        date_published=date_published,
        description=meta.meta_description,
        category=meta.category,
        content=body.get_content(),
    )


def atomic_write(path: Path, text: str) -> None:
    """Write via temp file + rename so a crash never leaves a truncated export."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def write_jsonl(path: Path, articles: Iterable[Article]) -> None:
    fetched_at = datetime.now(timezone.utc).isoformat()
    lines = []
    for article in articles:
        row = {
            "url": article.url,
            "slug": article.slug,
            "title": article.title,
            "date_published": article.date_published,
            "category": article.category,
            "description": article.description,
            "content": article.content,
            "fetched_at_utc": fetched_at,
        }
        lines.append(json.dumps(row, ensure_ascii=False) + "\n")
    atomic_write(path, "".join(lines))


def write_markdown(path: Path, articles: Iterable[Article]) -> None:
    chunks = []
    for article in articles:
        header = [f"# {article.title}", "", f"- URL: {article.url}"]
        if article.date_published:
            header.append(f"- Published: {article.date_published}")
        if article.category:
            header.append(f"- Category: {article.category}")
        if article.description:
            header.append(f"- Description: {article.description}")
        chunks.append("\n".join(header) + "\n\n" + article.content + "\n\n")
    atomic_write(path, "\n---\n\n".join(chunks))


def write_outputs(articles: list[Article], jsonl_path: Path, md_path: Path | None) -> None:
    write_jsonl(jsonl_path, articles)
    if md_path is not None:
        write_markdown(md_path, articles)
    print(f"Parsed {len(articles)} articles")
    print(f"JSONL: {jsonl_path.resolve()}")
    if md_path is not None:
        print(f"Markdown: {md_path.resolve()}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse ef-map blog into LLM-ready files")
    parser.add_argument("--jsonl", help="Output JSONL path (default depends on mode)")
    parser.add_argument("--markdown", help="Output Markdown path (default depends on mode)")
    parser.add_argument("--no-markdown", action="store_true", help="Skip markdown export")
    parser.add_argument("--article-html", help="Parse a single local article HTML file")
    parser.add_argument("--article-url", default=f"{BASE_URL}/blog/local-article", help="Source URL for --article-html mode")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout seconds")
    parser.add_argument("--retries", type=int, default=3, help="HTTP retry attempts per URL")
    parser.add_argument("--min-articles", type=int, default=5, help="Fail full crawl if fewer articles than this were parsed")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS certificate verification")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.article_html:
        html_path = Path(args.article_html)
        if not html_path.exists():
            print(f"Article file not found: {html_path}", file=sys.stderr)
            return 4
        html = html_path.read_text(encoding="utf-8")
        article = parse_article(args.article_url, html)
        articles = [article] if article.content else []
        if not articles:
            print("No article content extracted from local file.", file=sys.stderr)
            return 3

        # Default to separate files so single-article runs never clobber full-crawl exports.
        jsonl_path = Path(args.jsonl or "ef_map_blog_single_article.jsonl")
        md_path = None if args.no_markdown else Path(args.markdown or "ef_map_blog_single_article.md")
        write_outputs(articles, jsonl_path, md_path)
        return 0

    sitemap_xml: str | None = None
    index_html: str | None = None
    try:
        sitemap_xml = fetch_with_retry(
            SITEMAP_URL,
            timeout=args.timeout,
            insecure=args.insecure,
            retries=max(1, args.retries),
        )
    except Exception as exc:
        print(f"Warning: failed to fetch sitemap: {exc}", file=sys.stderr)
    try:
        index_html = fetch_with_retry(
            BLOG_INDEX,
            timeout=args.timeout,
            insecure=args.insecure,
            retries=max(1, args.retries),
        )
    except Exception as exc:
        print(f"Warning: failed to fetch blog index: {exc}", file=sys.stderr)

    if sitemap_xml is None and index_html is None:
        print("Failed to fetch both sitemap and blog index.", file=sys.stderr)
        return 1

    urls: set[str] = set()
    if sitemap_xml is not None:
        urls |= discover_from_sitemap(sitemap_xml)
    if index_html is not None:
        urls |= discover_from_index(index_html)
    urls = sorted(urls)

    if not urls:
        print("No blog article URLs found.", file=sys.stderr)
        return 2

    articles: list[Article] = []
    for url in urls:
        try:
            html = fetch_with_retry(
                url,
                timeout=args.timeout,
                insecure=args.insecure,
                retries=max(1, args.retries),
            )
            article = parse_article(url, html)
            if article.content:
                articles.append(article)
            else:
                print(f"Warning: empty content for {url}", file=sys.stderr)
        except Exception as exc:
            print(f"Warning: failed to parse {url}: {exc}", file=sys.stderr)

    if not articles:
        print("No article content extracted.", file=sys.stderr)
        return 3
    if len(articles) < max(1, args.min_articles):
        print(
            f"Parsed too few articles ({len(articles)} < {max(1, args.min_articles)}). "
            "Aborting to avoid writing a partial crawl.",
            file=sys.stderr,
        )
        return 5

    jsonl_path = Path(args.jsonl or "ef_map_blog_articles.jsonl")
    md_path = None if args.no_markdown else Path(args.markdown or "ef_map_blog_articles.md")
    write_outputs(articles, jsonl_path, md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
