#!/usr/bin/env python3
"""Scrape ef-map blog posts into LLM-friendly files (JSONL/Markdown)."""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
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
        if href.startswith("/blog/"):
            self.links.add(urljoin(BASE_URL, href))
        elif href.startswith("https://ef-map.com/blog/"):
            self.links.add(href)


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
        text = compact_spaces(unescape(data))
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
    BLOCK_TAGS = {"p", "h2", "h3", "h4", "li", "blockquote"}

    def __init__(self) -> None:
        super().__init__()
        self.in_article = False
        self.article_depth = 0
        self.current_tag: str | None = None
        self.current_parts: list[str] = []
        self.lines: list[str] = []
        self.list_depth = 0
        self.current_link: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        cls = attr_map.get("class") or ""

        if tag == "article" and "content" in cls.split():
            self.in_article = True
            self.article_depth = 1
            return

        if not self.in_article:
            return

        if tag == "article":
            self.article_depth += 1
            return

        if tag in ("ul", "ol"):
            self.list_depth += 1

        if tag == "a":
            href = attr_map.get("href")
            self.current_link = urljoin(BASE_URL, href) if href else None

        if tag in self.BLOCK_TAGS:
            self.current_tag = tag
            self.current_parts = []

        if tag == "br":
            self.current_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if not self.in_article:
            return

        if tag == "article":
            self.article_depth -= 1
            if self.article_depth <= 0:
                self.in_article = False
            return

        if tag in ("ul", "ol") and self.list_depth > 0:
            self.list_depth -= 1

        if tag == "a":
            self.current_link = None

        if tag in self.BLOCK_TAGS and self.current_tag == tag:
            text = compact_spaces("".join(self.current_parts))
            if text:
                if tag == "h2":
                    self.lines.append(f"## {text}")
                elif tag == "h3":
                    self.lines.append(f"### {text}")
                elif tag == "h4":
                    self.lines.append(f"#### {text}")
                elif tag == "li":
                    indent = "  " * max(0, self.list_depth - 1)
                    self.lines.append(f"{indent}- {text}")
                elif tag == "blockquote":
                    self.lines.append(f"> {text}")
                else:
                    self.lines.append(text)
            self.current_tag = None
            self.current_parts = []

    def handle_data(self, data: str) -> None:
        if not self.in_article:
            return
        text = unescape(data)
        if not text.strip() and "\n" not in text:
            return

        if self.current_link and text.strip():
            txt = compact_spaces(text)
            if self.current_link.startswith("/"):
                link = urljoin(BASE_URL, self.current_link)
            else:
                link = self.current_link
            self.current_parts.append(f"{txt} ({link})")
            return

        self.current_parts.append(text)

    def get_content(self) -> str:
        cleaned: list[str] = []
        prev_blank = False
        for line in self.lines:
            line = line.strip()
            if not line:
                if not prev_blank:
                    cleaned.append("")
                prev_blank = True
            else:
                cleaned.append(line)
                prev_blank = False
        return "\n\n".join([line for line in cleaned if line is not None]).strip()


def discover_from_sitemap(xml_text: str) -> set[str]:
    urls: set[str] = set()
    root = ET.fromstring(xml_text)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    for loc in root.findall("sm:url/sm:loc", ns):
        if not loc.text:
            continue
        link = loc.text.strip()
        if "/blog/" not in link:
            continue
        if link.rstrip("/") == BLOG_INDEX.rstrip("/"):
            continue
        urls.add(link)
    return urls


def discover_from_index(index_html: str) -> set[str]:
    parser = LinkCollector()
    parser.feed(index_html)
    links = {
        link
        for link in parser.links
        if urlparse(link).path.startswith("/blog/") and link.rstrip("/") != BLOG_INDEX.rstrip("/")
    }
    return links


def parse_article(url: str, html: str) -> Article:
    meta = MetadataParser()
    meta.feed(html)

    body = ArticleContentParser()
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


def write_jsonl(path: Path, articles: Iterable[Article]) -> None:
    fetched_at = datetime.now(timezone.utc).isoformat()
    with path.open("w", encoding="utf-8") as f:
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
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_markdown(path: Path, articles: Iterable[Article]) -> None:
    items = list(articles)
    total = len(items)
    with path.open("w", encoding="utf-8") as f:
        for idx, article in enumerate(items, start=1):
            f.write(f"# {article.title}\n\n")
            f.write(f"- URL: {article.url}\n")
            if article.date_published:
                f.write(f"- Published: {article.date_published}\n")
            if article.category:
                f.write(f"- Category: {article.category}\n")
            if article.description:
                f.write(f"- Description: {article.description}\n")
            f.write("\n")
            f.write(article.content)
            f.write("\n\n")
            if idx < total:
                f.write("\n---\n\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse ef-map blog into LLM-ready files")
    parser.add_argument("--jsonl", default="ef_map_blog_articles.jsonl", help="Output JSONL path")
    parser.add_argument("--markdown", default="ef_map_blog_articles.md", help="Output Markdown path")
    parser.add_argument("--no-markdown", action="store_true", help="Skip markdown export")
    parser.add_argument("--article-html", help="Parse a single local article HTML file")
    parser.add_argument("--article-url", default=f"{BASE_URL}/blog/local-article", help="Source URL for --article-html mode")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout seconds")
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

        jsonl_path = Path(args.jsonl)
        write_jsonl(jsonl_path, articles)

        if not args.no_markdown:
            md_path = Path(args.markdown)
            write_markdown(md_path, articles)

        print(f"Parsed {len(articles)} articles")
        print(f"JSONL: {jsonl_path.resolve()}")
        if not args.no_markdown:
            print(f"Markdown: {Path(args.markdown).resolve()}")
        return 0

    try:
        sitemap_xml = fetch(SITEMAP_URL, timeout=args.timeout, insecure=args.insecure)
        index_html = fetch(BLOG_INDEX, timeout=args.timeout, insecure=args.insecure)
    except Exception as exc:
        print(f"Failed to fetch index/sitemap: {exc}", file=sys.stderr)
        return 1

    urls = discover_from_sitemap(sitemap_xml) | discover_from_index(index_html)
    urls = sorted(urls)

    if not urls:
        print("No blog article URLs found.", file=sys.stderr)
        return 2

    articles: list[Article] = []
    for url in urls:
        try:
            html = fetch(url, timeout=args.timeout, insecure=args.insecure)
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

    jsonl_path = Path(args.jsonl)
    write_jsonl(jsonl_path, articles)

    if not args.no_markdown:
        md_path = Path(args.markdown)
        write_markdown(md_path, articles)

    print(f"Parsed {len(articles)} articles")
    print(f"JSONL: {jsonl_path.resolve()}")
    if not args.no_markdown:
        print(f"Markdown: {Path(args.markdown).resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
