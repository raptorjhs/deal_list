#!/usr/bin/env python3
"""
WSJ M&A headline scraper.

Fetches public WSJ RSS feeds (more reliable than the JS-protected
https://www.wsj.com/business/deals page), keeps only merger /
acquisition / deal headlines, extracts Company A / Company B from
the headline text, and writes JSON.

No third-party packages required (stdlib only).

Usage:
  python scrape_wsj_ma.py
  python scrape_wsj_ma.py --output deals.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path


FEEDS = [
    "https://feeds.content.dowjones.io/public/rss/WSJcomUSBusiness",
    "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
    "https://feeds.content.dowjones.io/public/rss/RSSWSJD",
]

MA_POSITIVE = re.compile(
    r"\b("
    r"merger|merge|merging|"
    r"acquisition|acquire|acquires|acquired|acquiring|"
    r"takeover|buyout|buy-out|"
    r"to buy|to acquire|"
    r"combination|combine|"
    r"take-private|take private|"
    r"spin-?off|divest"
    r")\b",
    re.IGNORECASE,
)

# Weaker deal language is only accepted if the URL is clearly a deals article
WEAK_DEAL = re.compile(
    r"\b(deal|offer|bid|to sell|sells|sold|stake)\b",
    re.IGNORECASE,
)

MA_NEGATIVE = re.compile(
    r"\b("
    r"trade deal|cloud deal|licensing deal|content deal|supply deal|"
    r"labor|union|factory|workers|"
    r"stock|shares rise|ipo|"
    r"news quiz|podcast|opinion|guidance"
    r")\b",
    re.IGNORECASE,
)

PAIR_PATTERNS = [
    re.compile(
        r"^(?P<a>[^,]+),\s+(?P<b>.+?)\s+Shares\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<a>.+?)\s+and\s+(?P<b>.+?)\s+(?:agree|agrees|announce|announces|plan|plans)\s+to\s+(?:merge|combine)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<a>.+?)\s+to\s+merge\s+with\s+(?P<b>.+?)(?:\s+in\b|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<a>.+?)\s+to\s+combine\s+with\s+(?P<b>.+?)(?:\s+to\b|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<a>.+?)\s+(?:to\s+)?(?:buy|acquire|acquires|acquired)\s+(?P<b>.+?)(?:\s+for\b|\s+in\b|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<a>.+?)\s+is\s+in\s+talks\s+to\s+(?:buy|sell|acquire)\s+(?:its\s+.+?\s+to\s+)?(?P<b>.+?)(?:\s+for\b|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<a>.+?)\s+in\s+(?:advanced\s+)?talks\s+to\s+buy\s+(?P<b>.+?)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<a>.+?)\s+rejects?\s+(?P<b>.+?)\s+(?:offer|bid)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<a>.+?)(?:'s)?\s+\$?[\d.]+\s+billion\s+takeover\s+bid.+\b(?P<b>[A-Z][\w.&' -]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<a>.+?)\s+(?:inks|signs|agrees).+sell.+\s+to\s+(?P<b>.+?)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<a>.+?)-[Oo]wned\s+.+\s+to\s+buy\s+(?P<b>.+?)$",
        re.IGNORECASE,
    ),
]


def is_ma(title: str, link: str) -> bool:
    if re.search(r"\bipo\b", title, re.I) and not re.search(r"\b(merger|acquire|acquisition|takeover)\b", title, re.I):
        return False
    if MA_NEGATIVE.search(title) and not MA_POSITIVE.search(title):
        return False
    if MA_POSITIVE.search(title):
        return True
    if "/business/deals/" in (link or "").lower() and WEAK_DEAL.search(title):
        return True
    return False


def clean_company(name: str) -> str:
    name = re.sub(r"\s+", " ", (name or "").strip())
    name = re.sub(
        r"\s+(?:for|in|to create|valued at|worth).+$",
        "",
        name,
        flags=re.IGNORECASE,
    )
    name = re.sub(r"^(?:its|the)\s+", "", name, flags=re.IGNORECASE)
    return name.strip(" -–—,;:")


def extract_companies(title: str) -> tuple[str, str]:
    for pat in PAIR_PATTERNS:
        m = pat.search(title)
        if m:
            a = clean_company(m.group("a"))
            b = clean_company(m.group("b"))
            if a and b and a.lower() != b.lower():
                return a, b

    fallback = re.split(
        r"\s+(?:to buy|to acquire|acquires|acquired|to merge with|to combine with|rejects|sells|to sell)\s+",
        title,
        maxsplit=1,
        flags=re.IGNORECASE,
    )
    if len(fallback) == 2:
        a = clean_company(fallback[0])
        b = clean_company(re.split(r"\s+for\s+|\s+in\s+", fallback[1], maxsplit=1)[0])
        if a and b:
            return a, b
    return "", ""


def google_news_link(company_a: str, company_b: str) -> str:
    """Build a Google News search URL using quoted company names."""
    terms = []
    if company_a:
        terms.append(f'"{company_a}"')
    if company_b:
        terms.append(f'"{company_b}"')
    query = " ".join(terms).strip() or '""'
    encoded = urllib.parse.quote(query)
    return (
        "https://news.google.com/search?"
        f"q={encoded}&hl=en-US&gl=US&ceid=US:en"
    )


def normalize_time(pub: str) -> str:
    pub = (pub or "").strip()
    if not pub:
        return ""
    try:
        dt = parsedate_to_datetime(pub)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return pub


def fetch_rss(url: str) -> list[dict]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; WSJ-MA-Bot/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    root = ET.fromstring(raw)
    items = []
    for item in root.findall("./channel/item"):
        items.append(
            {
                "title": (item.findtext("title") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
                "pub": (item.findtext("pubDate") or "").strip(),
            }
        )
    return items


def fetch_entries() -> list[dict]:
    seen: set[str] = set()
    rows: list[dict] = []

    for url in FEEDS:
        print(f"Fetching {url} ...")
        try:
            entries = fetch_rss(url)
        except Exception as exc:
            print(f"  warning: {exc}", file=sys.stderr)
            continue

        kept = 0
        for entry in entries:
            title = entry["title"]
            link = entry["link"]
            key = re.sub(r"\s+", " ", title).lower()
            if not title or not link or key in seen:
                continue
            if not is_ma(title, link):
                continue
            company_a, company_b = extract_companies(title)
            # Extra fallback: "X Merger" mentioned later in the headline
            if not company_b:
                m = re.search(r"as\s+\$?[\d.]+\s+billion\s+(?P<b>.+?)\s+Merger", title, re.I)
                if m:
                    company_b = clean_company(m.group("b"))
                    if not company_a:
                        company_a = clean_company(title.split()[0])
            rows.append(
                {
                    "company_a": company_a,
                    "company_b": company_b,
                    "headline": title,
                    "link": google_news_link(company_a, company_b),
                    "time": normalize_time(entry["pub"]),
                }
            )
            seen.add(key)
            kept += 1
        print(f"  kept {kept} M&A items from this feed")

    rows.sort(key=lambda r: r.get("time") or "", reverse=True)
    return rows


def deal_key(row: dict) -> str:
    headline = re.sub(r"\s+", " ", (row.get("headline") or "").lower()).strip()
    if headline:
        return "h:" + headline
    pair = (
        (row.get("company_a") or "").strip().lower()
        + "|"
        + (row.get("company_b") or "").strip().lower()
    )
    return "p:" + pair


def load_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict) and isinstance(data.get("deals"), list):
        return [row for row in data["deals"] if isinstance(row, dict)]
    return []


def merge_rows(existing: list[dict], incoming: list[dict]) -> tuple[list[dict], int]:
    existing_keys = {deal_key(row) for row in existing}
    added = sum(1 for row in incoming if deal_key(row) not in existing_keys)
    out: list[dict] = []
    seen: set[str] = set()
    for row in incoming + existing:
        key = deal_key(row)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out, added


def write_deals(path: Path, rows: list[dict]) -> None:
    payload = {"updated": date.today().isoformat(), "deals": rows}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape WSJ M&A headlines to JSON")
    parser.add_argument("--output", "-o", default="deals.json", help="Output JSON path")
    parser.add_argument("--replace", action="store_true", help="Overwrite instead of merge")
    args = parser.parse_args()

    rows = fetch_entries()
    out = Path(args.output)
    existing = [] if args.replace else load_existing(out)

    if not rows and not existing:
        print("No M&A headlines found.", file=sys.stderr)
        sys.exit(1)

    if args.replace:
        merged = rows
        added = len(rows)
    else:
        merged, added = merge_rows(existing, rows)

    write_deals(out, merged)
    print(
        f"\nWrote {len(merged)} deals ({added} new) → {out.resolve()}"
    )


if __name__ == "__main__":
    main()
