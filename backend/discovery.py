"""
discovery.py – Production URL harvester

Uses the Devpost JSON API to discover open hackathon URLs reliably.
Returns both URLs and structured metadata from the API.
Falls back to RSS parsing for non-Devpost feed URLs.
"""

from __future__ import annotations

import os
import re
import ssl
import asyncio
from typing import Dict, List, Optional, Tuple

import feedparser

# ---------------------------------------------------------------------------
# Configuration – read from environment
# ---------------------------------------------------------------------------
_RAW_FEEDS = os.getenv("DISCOVERY_FEEDS", "https://devpost.com/hackathons")
RSS_FEED_URLS: List[str] = [u.strip() for u in _RAW_FEEDS.split(",") if u.strip()]

# Global SSL bypass for standard library HTTP requests on macOS
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

_BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


# ---------------------------------------------------------------------------
# Devpost JSON API discovery (primary strategy)
# ---------------------------------------------------------------------------

def _parse_devpost_dates(date_str: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse Devpost 'submission_period_dates' like 'May 05 - Jun 11, 2026'
    into (start_date, end_date) in YYYY-MM-DD format.
    """
    import re
    from datetime import datetime

    if not date_str:
        return None, None

    # Pattern: "Mon DD - Mon DD, YYYY" or "Mon DD, YYYY - Mon DD, YYYY"
    # Try splitting on " - "
    parts = date_str.split(" - ")
    if len(parts) != 2:
        return None, None

    start_raw = parts[0].strip()
    end_raw = parts[1].strip()

    # The year may only appear in the end part
    year_match = re.search(r'\d{4}', end_raw)
    year = year_match.group(0) if year_match else None
    if not year:
        return None, None

    # If start_raw doesn't have a year, append it
    if not re.search(r'\d{4}', start_raw):
        start_raw = f"{start_raw}, {year}"

    # Try parsing
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y"):
        try:
            start_dt = datetime.strptime(start_raw, fmt)
            end_dt = datetime.strptime(end_raw, fmt)
            return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None, None


def _clean_prize(prize_html: str) -> str:
    """Strip HTML tags from Devpost prize_amount like '$<span data-currency-value>60,000</span>'."""
    if not prize_html:
        return "See listing"
    cleaned = re.sub(r'<[^>]+>', '', prize_html)
    return cleaned.strip() or "See listing"


def _devpost_api_discover(max_pages: int = 3) -> List[Dict]:
    """
    Hit the Devpost public JSON API to get open hackathons with metadata.
    Returns a list of dicts with url + structured metadata.
    """
    import httpx
    results: List[Dict] = []

    for page in range(1, max_pages + 1):
        api_url = f"https://devpost.com/api/hackathons?status=open&page={page}"
        try:
            print(f"[~] Fetching Devpost API page {page}: {api_url}")
            resp = httpx.get(
                api_url,
                headers={"User-Agent": _BROWSER_UA, "Accept": "application/json"},
                verify=False,
                timeout=15.0,
            )
            if resp.status_code != 200:
                print(f"[-] Devpost API HTTP {resp.status_code} on page {page}")
                break

            data = resp.json()
            hackathons = data.get("hackathons", [])
            if not hackathons:
                print(f"[~] Devpost API page {page}: no more hackathons.")
                break

            for h in hackathons:
                url = h.get("url")
                if not url:
                    continue

                start_date, end_date = _parse_devpost_dates(h.get("submission_period_dates", ""))
                themes = [t["name"] for t in h.get("themes", []) if "name" in t]

                results.append({
                    "url": url,
                    "title": h.get("title", ""),
                    "organizer": h.get("organization_name", ""),
                    "prize": _clean_prize(h.get("prize_amount", "")),
                    "start_date": start_date,
                    "end_date": end_date,
                    "deadline": end_date,  # submission deadline = end date on Devpost
                    "tags": themes,
                    "time_left": h.get("time_left_to_submission", ""),
                    "registrations": h.get("registrations_count", 0),
                })

            print(f"[+] Devpost API page {page}: got {len(hackathons)} hackathons")
        except Exception as e:
            print(f"[!] Devpost API error on page {page}: {e}")
            break

    print(f"[+] Devpost API total: {len(results)} hackathon entries discovered")
    return results


# ---------------------------------------------------------------------------
# RSS parsing (feedparser) – for non-Devpost feeds
# ---------------------------------------------------------------------------

def _rss_links_from_feed(feed_url: str) -> List[Dict]:
    """Attempt to parse feed_url as RSS/Atom. Returns list of dicts with url key."""
    try:
        import httpx
        headers = {"User-Agent": _BROWSER_UA}
        print(f"[~] Fetching RSS feed: {feed_url}")
        response = httpx.get(feed_url, headers=headers, verify=False, timeout=15.0)

        if response.status_code != 200:
            print(f"[-] RSS feed HTTP error: status code {response.status_code} for {feed_url}")
            return []

        parsed = feedparser.parse(response.text)
        results: List[Dict] = []
        for entry in parsed.entries:
            url = entry.get("link") or entry.get("guid") or entry.get("id")
            if url:
                results.append({"url": url})
        if results:
            print(f"[+] RSS feed parsed: {len(results)} entries from {feed_url}")
        return results
    except Exception as e:
        print(f"[!] feedparser exception on {feed_url}: {e}")
        return []


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

# Module-level metadata cache — pipeline reads this after discovery
_api_metadata: Dict[str, Dict] = {}


def get_api_metadata(url: str) -> Optional[Dict]:
    """Get pre-fetched API metadata for a URL, if available."""
    return _api_metadata.get(url)


async def discover_new_hackathons_async() -> List[str]:
    """
    Async version: uses Devpost JSON API for devpost.com feeds,
    RSS parsing for other feeds. Returns a de-duplicated list of URLs.
    Also caches API metadata for later use by the pipeline.
    """
    global _api_metadata
    all_entries: List[Dict] = []

    for feed_url in RSS_FEED_URLS:
        if "devpost.com" in feed_url:
            loop = asyncio.get_event_loop()
            entries = await loop.run_in_executor(None, _devpost_api_discover, 3)
            all_entries.extend(entries)
        else:
            rss_entries = _rss_links_from_feed(feed_url)
            all_entries.extend(rss_entries)

    # De-duplicate while preserving order, and cache metadata
    seen: set = set()
    unique_urls: List[str] = []
    for entry in all_entries:
        url = entry["url"]
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
            _api_metadata[url] = entry

    return unique_urls


def discover_new_hackathons() -> List[str]:
    """
    Synchronous wrapper around the async discovery function.
    Safe to call from non-async contexts.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, discover_new_hackathons_async())
                return future.result()
        else:
            return loop.run_until_complete(discover_new_hackathons_async())
    except RuntimeError:
        return asyncio.run(discover_new_hackathons_async())
