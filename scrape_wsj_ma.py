#!/usr/bin/env python3
"""
Collect M&A headlines and write deals.json.

Source order:
  1. https://www.wsj.com/business/deals  (HTML titles)
  2. Public WSJ RSS feeds, if the website blocks the request

Each row:
  name     Company A / Company B
  summary  Article title
  date     DD MMM YYYY
  link     Google News search for the deal name

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
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path


WSJ_DEALS_URL = "https://www.wsj.com/business/deals"
WSJ_RSS = [
    "https://feeds.content.dowjones.io/public/rss/WSJcomUSBusiness",
    "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
    "https://feeds.content.dowjones.io/public/rss/RSSWSJD",
]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

MA_WORDS = re.compile(
    r"\b(merger|merge|merging|acquisition|acquire|acquires|acquired|acquiring|"
    r"takeover|buyout|buy-out|to buy|to acquire|combination|combine|"
    r"take-private|take private|spin-?off|divest)\b",
    re.I,
)
WEAK_DEAL = re.compile(r"\b(deal|offer|bid|to sell|sells|sold|stake)\b", re.I)
SKIP_WORDS = re.compile(
    r"\b(trade deal|cloud deal|licensing deal|content deal|supply deal|"
    r"labor|union|factory|workers|ipo|news quiz|podcast|opinion|guidance)\b",
    re.I,
)
PAIR_PATTERNS = [
    re.compile(r"^(?P<a>[^,]+),\s+(?P<b>.+?)\s+Shares\b", re.I),
    re.compile(r"^(?P<a>.+?)\s+and\s+(?P<b>.+?)\s+(?:agree|agrees|announce|announces|plan|plans)\s+to\s+(?:merge|combine)", re.I),
    re.compile(r"^(?P<a>.+?)\s+to\s+merge\s+with\s+(?P<b>.+?)(?:\s+in\b|$)", re.I),
    re.compile(r"^(?P<a>.+?)\s+to\s+combine\s+with\s+(?P<b>.+?)(?:\s+to\b|$)", re.I),
    re.compile(r"^(?P<a>.+?)\s+(?:to\s+)?(?:buy|acquire|acquires|acquired)\s+(?P<b>.+?)(?:\s+for\b|\s+in\b|$)", re.I),
    re.compile(r"^(?P<a>.+?)\s+is\s+in\s+talks\s+to\s+(?:buy|sell|acquire)\s+(?:its\s+.+?\s+to\s+)?(?P<b>.+?)(?:\s+for\b|$)", re.I),
    re.compile(r"^(?P<a>.+?)\s+in\s+(?:advanced\s+)?talks\s+to\s+buy\s+(?P<b>.+?)$", re.I),
    re.compile(r"^(?P<a>.+?)\s+rejects?\s+(?P<b>.+?)\s+(?:offer|bid)", re.I),
    re.compile(r"^(?P<a>.+?)(?:'s)?\s+\$?[\d.]+\s+billion\s+takeover\s+bid.+\b(?P<b>[A-Z][\w.&' -]+)", re.I),
    re.compile(r"^(?P<a>.+?)\s+(?:inks|signs|agrees).+sell.+\s+to\s+(?P<b>.+?)$", re.I),
]


def format_date(value: str | None) -> str:
    """Return DD MMM YYYY."""
    text = (value or "").strip()
    if not text:
        now = datetime.now(timezone.utc)
        return f"{now.day} {MONTHS[now.month - 1]} {now.year}"
    try:
        dt = parsedate_to_datetime(text)
    except Exception:
        dt = None
    if dt is None:
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return text
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return f"{dt.day} {MONTHS[dt.month - 1]} {dt.year}"


def google_news_link(name: str) -> str:
    query = urllib.parse.quote(name.strip())
    return f"https://news.google.com/search?q={query}&hl=en-US&gl=US&ceid=US:en"


def is_ma(title: str, url: str = "") -> bool:
    if SKIP_WORDS.search(title) and not MA_WORDS.search(title):
        return False
    if MA_WORDS.search(title):
        return True
    if "/business/deals/" in (url or "").lower() and WEAK_DEAL.search(title):
        return True
    return False


def clean_company(name: str) -> str:
    name = re.sub(r"\s+", " ", unescape(name or "").strip())
    name = re.sub(r"\s+(?:for|in|to create|valued at|worth).+$", "", name, flags=re.I)
    name = re.sub(r"^(?:its|the)\s+", "", name, flags=re.I)
    return name.strip(" -–—,;:")


def deal_name(title: str) -> str:
    for pat in PAIR_PATTERNS:
        match = pat.search(title)
        if match:
            left = clean_company(match.group("a"))
            right = clean_company(match.group("b"))
            if left and right and left.lower() != right.lower():
                return f"{left} / {right}"
    parts = re.split(
        r"\s+(?:to buy|to acquire|acquires|acquired|to merge with|to combine with|rejects|sells|to sell)\s+",
        title,
        maxsplit=1,
        flags=re.I,
    )
    if len(parts) == 2:
        left = clean_company(parts[0])
        right = clean_company(re.split(r"\s+for\s+|\s+in\s+", parts[1], maxsplit=1)[0])
        if left and right:
            return f"{left} / {right}"
    return clean_company(title) or title


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def titles_from_html(html: str) -> list[str]:
    titles: list[str] = []
    seen: set[str] = set()
    patterns = [
        r'"headline"\s*:\s*"([^"]{12,180})"',
        r"<h[23][^>]*>\s*(?:<a[^>]*>)?([^<]{12,180})",
        r'href="https://www\.wsj\.com/business/deals/[^"]+"[^>]*>([^<]{12,180})',
    ]
    for pattern in patterns:
        for raw in re.findall(pattern, html, flags=re.I):
            title = unescape(re.sub(r"\s+", " ", raw)).strip()
            key = title.lower()
            if key in seen or title.lower() in {"latest news", "more in deals"}:
                continue
            seen.add(key)
            titles.append(title)
    return titles


def from_wsj_website() -> list[dict]:
    print(f"Fetching {WSJ_DEALS_URL} ...")
    html = fetch(WSJ_DEALS_URL).decode("utf-8", "replace")
    titles = titles_from_html(html)
    rows = []
    today = format_date("")
    for title in titles:
        if not is_ma(title, WSJ_DEALS_URL):
            continue
        name = deal_name(title)
        rows.append(
            {
                "name": name,
                "summary": title,
                "date": today,
                "link": google_news_link(name),
            }
        )
    print(f"  kept {len(rows)} M&A titles from the website")
    return rows


def from_wsj_rss() -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for url in WSJ_RSS:
        print(f"Fetching {url} ...")
        try:
            xml = fetch(url)
        except Exception as exc:
            print(f"  warning: {exc}", file=sys.stderr)
            continue
        root = ET.fromstring(xml)
        kept = 0
        for item in root.findall("./channel/item"):
            title = (item.findtext("title") or "").strip()
            item_url = (item.findtext("link") or "").strip()
            key = re.sub(r"\s+", " ", title).lower()
            if not title or key in seen or not is_ma(title, item_url):
                continue
            name = deal_name(title)
            rows.append(
                {
                    "name": name,
                    "summary": title,
                    "date": format_date(item.findtext("pubDate") or ""),
                    "link": google_news_link(name),
                }
            )
            seen.add(key)
            kept += 1
        print(f"  kept {kept} M&A titles from this feed")
    return rows


def write_deals(path: Path, rows: list[dict]) -> None:
    payload = {
        "updated": format_date(""),
        "deals": rows,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a fresh deals.json from WSJ M&A titles")
    parser.add_argument("--output", "-o", default="deals.json")
    args = parser.parse_args()

    rows: list[dict] = []
    try:
        rows = from_wsj_website()
    except Exception as exc:
        print(f"WSJ website blocked or failed ({exc}). Falling back to public WSJ RSS.", file=sys.stderr)

    if not rows:
        rows = from_wsj_rss()

    if not rows:
        print("No M&A headlines found. Left existing file unchanged.", file=sys.stderr)
        sys.exit(1)

    out = Path(args.output)
    write_deals(out, rows)
    print(f"\nWrote {len(rows)} deals → {out.resolve()}")


if __name__ == "__main__":
    main()
