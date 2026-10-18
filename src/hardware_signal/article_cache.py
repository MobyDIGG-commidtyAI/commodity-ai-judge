"""Fetch linked news pages and cache extracted article text with provenance."""

import csv
import io
import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .config import OUTPUT_DIR, ROOT


CACHE_DIR = OUTPUT_DIR / "article_cache"
SNAPSHOT_DIR = OUTPUT_DIR / "page_snapshots"
OVERRIDES = ROOT / "data/article_url_overrides.csv"
MAX_HTML_BYTES = 4_000_000


class ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.article_depth = 0
        self.body_depth = 0
        self.main_depth = 0
        self.main_paragraphs = []
        self.paragraph_depth = 0
        self.paragraph = []
        self.paragraphs = []
        self.script_depth = 0
        self.script = []
        self.jsonld = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "article":
            self.article_depth += 1
        elif self.article_depth:
            self.article_depth += 1
        if "ArticleBody-articleBody" in attributes.get("class", ""):
            self.body_depth += 1
        elif self.body_depth:
            self.body_depth += 1
        if tag == "main":
            self.main_depth += 1
        elif self.main_depth:
            self.main_depth += 1
        if tag == "p" and (self.article_depth or self.body_depth or self.main_depth):
            self.paragraph_depth += 1
            self.paragraph = []
        if tag == "script" and attributes.get("type") == "application/ld+json":
            self.script_depth += 1
            self.script = []

    def handle_endtag(self, tag):
        if tag == "p" and self.paragraph_depth:
            value = " ".join(self.paragraph).strip()
            if value:
                if self.article_depth or self.body_depth:
                    self.paragraphs.append(value)
                if self.main_depth:
                    self.main_paragraphs.append(value)
            self.paragraph_depth -= 1
            self.paragraph = []
        if tag == "script" and self.script_depth:
            self.jsonld.append("".join(self.script))
            self.script_depth -= 1
            self.script = []
        if self.article_depth:
            self.article_depth -= 1
        if self.body_depth:
            self.body_depth -= 1
        if self.main_depth:
            self.main_depth -= 1

    def handle_data(self, data):
        if self.paragraph_depth and data.strip():
            self.paragraph.append(data.strip())
        if self.script_depth:
            self.script.append(data)


def metadata_from_jsonld(parser):
    webpage = {}
    for raw in parser.jsonld:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        entries = value if isinstance(value, list) else [value]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            graph = entry.get("@graph")
            candidates = graph if isinstance(graph, list) else [entry]
            for item in candidates:
                if isinstance(item, dict) and ("Article" in str(item.get("@type", ""))):
                    return {"headline": item.get("headline"),
                            "published_at": item.get("datePublished"),
                            "modified_at": item.get("dateModified")}
                if isinstance(item, dict) and item.get("@type") == "WebPage" and item.get("datePublished"):
                    webpage = {"headline": item.get("name"),
                               "published_at": item.get("datePublished"),
                               "modified_at": item.get("dateModified")}
    return webpage


def source_overrides():
    if not OVERRIDES.exists():
        return {}
    with OVERRIDES.open(newline="") as handle:
        return {row["article_id"]: row for row in csv.DictReader(handle)}


def safe_http_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("source URL must be HTTP(S)")
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("local source URL is not allowed")
    try:
        if not ip_address(host).is_global:
            raise ValueError("non-public source URL is not allowed")
    except ValueError as exc:
        if str(exc) == "non-public source URL is not allowed":
            raise
    return url


def fetch_article(article, opener=urlopen):
    override = source_overrides().get(article["id"])
    url = override["url"] if override else article.get("url", "")
    if not url:
        return {"article_id": article["id"], "status": "missing_url"}
    safe_http_url(url)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; HardwareSignalResearch/1.0)"})
    try:
        with opener(request, timeout=20) as response:
            content_type = response.headers.get("Content-Type", "")
            if "html" not in content_type.lower():
                return {"article_id": article["id"], "status": "non_html", "url": url}
            raw = response.read(MAX_HTML_BYTES + 1)
            if len(raw) > MAX_HTML_BYTES:
                return {"article_id": article["id"], "status": "too_large", "url": url}
            resolved = response.url
    except Exception as exc:
        return {"article_id": article["id"], "status": "fetch_error", "url": url,
                "error": f"{type(exc).__name__}: {exc}"[:200]}
    parser = ArticleParser()
    parser.feed(raw.decode("utf-8", "replace"))
    metadata = metadata_from_jsonld(parser)
    # Keep paragraph boundaries; exclude very short navigation fragments.
    paragraphs = [p for p in parser.paragraphs if len(p.split()) >= 5]
    if sum(len(p.split()) for p in paragraphs) < 100 and metadata.get("published_at"):
        main = [p for p in parser.main_paragraphs if len(p.split()) >= 5]
        if sum(len(p.split()) for p in main) >= 100:
            paragraphs = main
    body = "\n\n".join(paragraphs)
    word_count = len(body.split())
    published = metadata.get("published_at")
    if published and published[:7] > article["date"][:7]:
        status = "published_after_case_month"
    elif word_count < 100:
        status = "insufficient_text"
    else:
        status = "ok"
    result = {"article_id": article["id"], "status": status,
              "dataset_url": article.get("url", ""), "source_url": url,
              "resolved_url": resolved, "relationship": override["relationship"] if override else "dataset-url",
              "source_headline": metadata.get("headline"), "source_published_at": published,
              "source_modified_at": metadata.get("modified_at"),
              "dataset_published_date": article["date"],
              "fetched_at": datetime.now(timezone.utc).isoformat(),
              "word_count": word_count, "body": body if status == "ok" else ""}
    return result


def save_article(result):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{result['article_id']}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return path


def download_page_snapshot(article, opener=urlopen):
    """Keep the fetched source HTML even when article-body extraction fails."""
    override = source_overrides().get(article["id"])
    url = override["url"] if override else article.get("url", "")
    if not url:
        return {"article_id": article["id"], "status": "missing_url"}
    safe_http_url(url)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; HardwareSignalResearch/1.0)"})
    try:
        with opener(request, timeout=20) as response:
            if "html" not in response.headers.get("Content-Type", "").lower():
                return {"article_id": article["id"], "status": "non_html", "source_url": url}
            raw = response.read(MAX_HTML_BYTES + 1)
            if len(raw) > MAX_HTML_BYTES:
                return {"article_id": article["id"], "status": "too_large", "source_url": url}
            resolved = response.url
    except Exception as exc:
        return {"article_id": article["id"], "status": "fetch_error", "source_url": url,
                "error": f"{type(exc).__name__}: {exc}"[:200]}
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / f"{article['id']}.html"
    path.write_bytes(raw)
    return {"article_id": article["id"], "status": "saved", "source_url": url,
            "resolved_url": resolved, "snapshot_path": str(path), "bytes": len(raw),
            "fetched_at": datetime.now(timezone.utc).isoformat()}


def extract_article_snapshot(article):
    """Apply the article extractor to a previously downloaded HTML page."""
    path = SNAPSHOT_DIR / f"{article['id']}.html"
    if not path.exists():
        raise FileNotFoundError(path)

    class SnapshotResponse(io.BytesIO):
        headers = {"Content-Type": "text/html; charset=utf-8"}

        def __init__(self, raw, url):
            super().__init__(raw)
            self.url = url

    def opener(request, timeout):
        return SnapshotResponse(path.read_bytes(), request.full_url)

    result = fetch_article(article, opener=opener)
    result["snapshot_path"] = str(path)
    return result


def load_cached_article(article_id):
    path = CACHE_DIR / f"{article_id}.json"
    return json.loads(path.read_text()) if path.exists() else None


def with_article_text(case, max_chars_per_article=8000, max_total_chars=50000):
    """Return a case copy enriched only by cached, timely source articles."""
    news = []
    used_chars = 0
    for article in case["news"]:
        enriched = dict(article)
        cached = load_cached_article(article["id"])
        if cached and cached.get("status") == "ok":
            published = cached.get("source_published_at")
            if not published or published[:7] <= case["as_of_month"]:
                body = cached["body"][:max_chars_per_article]
                if used_chars + len(body) <= max_total_chars:
                    enriched["article_text"] = body
                    enriched["article_url"] = cached["source_url"]
                    # The feed timestamp is the case's observation date when the
                    # publisher page does not expose publication metadata.
                    enriched["article_published_at"] = published or article["date"]
                    enriched["article_date_source"] = "publisher" if published else "dataset"
                    enriched["content_status"] = "article_text"
                    enriched["content_truncated"] = len(body) < len(cached["body"])
                    used_chars += len(body)
                else:
                    enriched["content_status"] = "budget_excluded"
        if "content_status" not in enriched:
            enriched["content_status"] = cached.get("status", "not_fetched") if cached else "not_fetched"
        news.append(enriched)
    return {**case, "news": news}
