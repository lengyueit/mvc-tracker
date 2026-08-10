#!/usr/bin/env python3
"""
Daily MVC paper synchronizer.

The script is intentionally dependency-free so it can run in GitHub Actions,
cron, or a local shell without installing packages. It reads data/groups.json
and data/keywords.json, queries public scholarly APIs, merges new records into
data/papers.json, and writes data/sync_status.json.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
PAPERS_PATH = DATA_DIR / "papers.json"
GROUPS_PATH = DATA_DIR / "groups.json"
KEYWORDS_PATH = DATA_DIR / "keywords.json"
STATUS_PATH = DATA_DIR / "sync_status.json"

USER_AGENT = "mvc-tracker/0.1 (mailto:example@example.com)"
TODAY = dt.date.today().isoformat()
MVC_TERMS = (
    "multi-view clustering",
    "multiview clustering",
    "incomplete multi-view",
    "incomplete multiview",
    "partial multi-view",
    "contrastive multi-view",
    "anchor graph",
    "multiple kernel clustering",
    "multi-kernel clustering",
)


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def request_json(url: str, timeout: int = 25) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def request_text(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def slug(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:96] or hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def norm_title(title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", title.lower())).strip()


def paper_key(record: dict[str, Any]) -> str:
    if record.get("doi"):
        return "doi:" + record["doi"].lower()
    if record.get("semantic_scholar_id"):
        return "s2:" + record["semantic_scholar_id"]
    if record.get("openalex_id"):
        return "openalex:" + record["openalex_id"]
    if record.get("arxiv_id"):
        return "arxiv:" + record["arxiv_id"]
    return "title:" + norm_title(record.get("title", ""))


def is_mvc_related(title: str, abstract: str = "") -> bool:
    haystack = f"{title} {abstract}".lower()
    return any(term in haystack for term in MVC_TERMS)


def infer_topics(title: str, abstract: str = "") -> list[str]:
    haystack = f"{title} {abstract}".lower()
    rules = [
        ("IMVC", ("incomplete", "missing", "partial", "view-missing")),
        ("contrastive MVC", ("contrastive",)),
        ("anchor graph", ("anchor", "bipartite graph")),
        ("federated MVC", ("federated",)),
        ("continual MVC", ("continual", "incremental")),
        ("safe MVC", ("safe", "guarantee")),
        ("robust MVC", ("robust", "noise", "noisy correspondence")),
        ("multiple kernel clustering", ("multiple kernel", "multi-kernel")),
        ("deep MVC", ("deep", "neural", "representation")),
    ]
    topics = [label for label, keys in rules if any(k in haystack for k in keys)]
    return topics or ["MVC"]


def score_record(record: dict[str, Any]) -> int:
    text = f"{record.get('title', '')} {record.get('abstract', '')}".lower()
    score = 40
    for term in MVC_TERMS:
        if term in text:
            score += 8
    if record.get("code_url"):
        score += 5
    if record.get("pdf_url"):
        score += 3
    year = record.get("year")
    if isinstance(year, int) and year >= dt.date.today().year - 1:
        score += 5
    return min(score, 100)


def semantic_scholar_search(query: str, limit: int) -> list[dict[str, Any]]:
    fields = ",".join(
        [
            "paperId",
            "title",
            "abstract",
            "year",
            "venue",
            "authors",
            "externalIds",
            "openAccessPdf",
            "url",
        ]
    )
    params = urllib.parse.urlencode({"query": query, "limit": limit, "fields": fields})
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?{params}"
    data = request_json(url)
    out = []
    for item in data.get("data", []):
        title = item.get("title") or ""
        abstract = item.get("abstract") or ""
        if not title or not is_mvc_related(title, abstract):
            continue
        external = item.get("externalIds") or {}
        pdf = item.get("openAccessPdf") or {}
        out.append(
            {
                "title": title,
                "authors": [a.get("name", "") for a in item.get("authors", []) if a.get("name")],
                "year": item.get("year"),
                "venue": item.get("venue") or "",
                "doi": external.get("DOI") or "",
                "arxiv_id": external.get("ArXiv") or "",
                "semantic_scholar_id": item.get("paperId") or "",
                "openalex_id": "",
                "pdf_url": pdf.get("url") or item.get("url") or "",
                "code_url": "",
                "abstract": abstract,
                "source": ["semantic_scholar"],
            }
        )
    return out


def openalex_search(query: str, limit: int, from_year: int) -> list[dict[str, Any]]:
    filters = f"from_publication_date:{from_year}-01-01"
    params = urllib.parse.urlencode(
        {
            "search": query,
            "filter": filters,
            "per-page": limit,
            "sort": "publication_date:desc",
            "mailto": "example@example.com",
        }
    )
    url = f"https://api.openalex.org/works?{params}"
    data = request_json(url)
    out = []
    for item in data.get("results", []):
        title = item.get("title") or item.get("display_name") or ""
        abstract = openalex_abstract(item.get("abstract_inverted_index") or {})
        if not title or not is_mvc_related(title, abstract):
            continue
        venue = ""
        primary = item.get("primary_location") or {}
        source = primary.get("source") or {}
        if source:
            venue = source.get("display_name") or ""
        pdf_url = ""
        if primary.get("pdf_url"):
            pdf_url = primary["pdf_url"]
        elif primary.get("landing_page_url"):
            pdf_url = primary["landing_page_url"]
        out.append(
            {
                "title": title,
                "authors": [
                    a.get("author", {}).get("display_name", "")
                    for a in item.get("authorships", [])
                    if a.get("author", {}).get("display_name")
                ],
                "year": item.get("publication_year"),
                "venue": venue,
                "doi": (item.get("doi") or "").replace("https://doi.org/", ""),
                "arxiv_id": "",
                "semantic_scholar_id": "",
                "openalex_id": item.get("id") or "",
                "pdf_url": pdf_url,
                "code_url": "",
                "abstract": abstract,
                "source": ["openalex"],
            }
        )
    return out


def openalex_abstract(index: dict[str, list[int]]) -> str:
    if not index:
        return ""
    words: list[str] = [""] * (max(pos for positions in index.values() for pos in positions) + 1)
    for word, positions in index.items():
        for pos in positions:
            words[pos] = word
    return " ".join(words)


def arxiv_search(query: str, limit: int) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "search_query": f'all:"{query}"',
            "start": 0,
            "max_results": limit,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    text = request_text(f"https://export.arxiv.org/api/query?{params}")
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(text)
    out = []
    for entry in root.findall("a:entry", ns):
        title = re.sub(r"\s+", " ", html.unescape(entry.findtext("a:title", "", ns))).strip()
        abstract = re.sub(r"\s+", " ", html.unescape(entry.findtext("a:summary", "", ns))).strip()
        if not title or not is_mvc_related(title, abstract):
            continue
        arxiv_url = entry.findtext("a:id", "", ns)
        arxiv_id = arxiv_url.rsplit("/", 1)[-1]
        published = entry.findtext("a:published", "", ns)
        year = int(published[:4]) if published[:4].isdigit() else None
        authors = [a.findtext("a:name", "", ns) for a in entry.findall("a:author", ns)]
        out.append(
            {
                "title": title,
                "authors": [a for a in authors if a],
                "year": year,
                "venue": "arXiv",
                "doi": "",
                "arxiv_id": arxiv_id,
                "semantic_scholar_id": "",
                "openalex_id": "",
                "pdf_url": arxiv_url.replace("/abs/", "/pdf/"),
                "code_url": "",
                "abstract": abstract,
                "source": ["arxiv"],
            }
        )
    return out


def choose_team(record: dict[str, Any], groups: list[dict[str, Any]]) -> str:
    author_names = {a.lower() for a in record.get("authors", [])}
    for group in groups:
        for author in group.get("authors", []):
            if author.get("name", "").lower() in author_names:
                return group["id"]
    return "unknown"


def complete_record(record: dict[str, Any], groups: list[dict[str, Any]]) -> dict[str, Any]:
    title = record.get("title", "").strip()
    record["id"] = record.get("id") or f"{record.get('year') or 'paper'}-{slug(title)}"
    record["team"] = record.get("team") or choose_team(record, groups)
    record["topic"] = record.get("topic") or infer_topics(title, record.get("abstract", ""))
    record["first_seen"] = record.get("first_seen") or TODAY
    record["last_checked"] = TODAY
    record["status"] = record.get("status") or "new"
    record["relevance_score"] = record.get("relevance_score") or score_record(record)
    return record


def merge_records(existing: list[dict[str, Any]], incoming: list[dict[str, Any]], groups: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    by_key = {paper_key(item): item for item in existing if paper_key(item) != "title:"}
    added = 0
    for raw in incoming:
        item = complete_record(raw, groups)
        key = paper_key(item)
        if key in by_key:
            current = by_key[key]
            for field in ["doi", "arxiv_id", "semantic_scholar_id", "openalex_id", "pdf_url", "code_url", "abstract", "venue"]:
                if not current.get(field) and item.get(field):
                    current[field] = item[field]
            current["last_checked"] = TODAY
            current["source"] = sorted(set(current.get("source", [])) | set(item.get("source", [])))
            current["topic"] = sorted(set(current.get("topic", [])) | set(item.get("topic", [])))
        else:
            by_key[key] = item
            added += 1
    result = list(by_key.values())
    result.sort(key=lambda p: (p.get("year") or 0, p.get("first_seen") or ""), reverse=True)
    return result, added


def collect(limit: int, from_year: int, groups: list[dict[str, Any]], keywords: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    queries = list(dict.fromkeys(keywords[:8] + [f'{a["name"]} multi-view clustering' for g in groups for a in g.get("authors", [])]))
    for query in queries:
        for label, func in [
            ("semantic_scholar", lambda q: semantic_scholar_search(q, limit)),
            ("openalex", lambda q: openalex_search(q, limit, from_year)),
            ("arxiv", lambda q: arxiv_search(q, min(limit, 10))),
        ]:
            try:
                records.extend(func(query))
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ET.ParseError, json.JSONDecodeError) as exc:
                errors.append(f"{label}: {query}: {exc}")
            time.sleep(1.0)
    return records, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=8, help="Results per query per source.")
    parser.add_argument("--from-year", type=int, default=dt.date.today().year - 3)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    groups = load_json(GROUPS_PATH, [])
    keywords = load_json(KEYWORDS_PATH, [])
    existing = load_json(PAPERS_PATH, [])
    incoming, errors = collect(args.limit, args.from_year, groups, keywords)
    merged, added = merge_records(existing, incoming, groups)

    status = {
        "date": TODAY,
        "existing_before": len(existing),
        "fetched": len(incoming),
        "added": added,
        "total_after": len(merged),
        "errors": errors[:25],
    }

    if not args.dry_run:
        save_json(PAPERS_PATH, merged)
        save_json(STATUS_PATH, status)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
