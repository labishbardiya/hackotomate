"""
discovery.py – Production URL harvester

Uses the Devpost JSON API to discover open hackathon URLs reliably.
Falls back to deep-crawl for non-Devpost feed URLs.
"""

from __future__ import annotations

import os
import re
import ssl
import asyncio
from typing import List

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

def _devpost_api_links(max_pages: int = 3) -> List[str]:
    """
    Hit the Devpost public JSON API to get open hackathon URLs.
    Returns a list of hackathon page URLs (e.g. https://rapid-agent.devpost.com/).
    """
    import httpx
    all_urls: List[str] = []

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
                if url:
                    all_urls.append(url)

            print(f"[+] Devpost API page {page}: got {len(hackathons)} hackathons")
        except Exception as e:
            print(f"[!] Devpost API error on page {page}: {e}")
            break

    print(f"[+] Devpost API total: {len(all_urls)} hackathon URLs discovered")
    return all_urls


# ---------------------------------------------------------------------------
# RSS parsing (feedparser) – for non-Devpost feeds
# ---------------------------------------------------------------------------

def _rss_links_from_feed(feed_url: str) -> List[str]:
    """Attempt to parse feed_url as RSS/Atom. Returns [] if no entries found."""
    try:
        import httpx
        headers = {"User-Agent": _BROWSER_UA}
        print(f"[~] Fetching RSS feed: {feed_url}")
        response = httpx.get(feed_url, headers=headers, verify=False, timeout=15.0)

        if response.status_code != 200:
            print(f"[-] RSS feed HTTP error: status code {response.status_code} for {feed_url}")
            return []

        parsed = feedparser.parse(response.text)
        links: List[str] = []
        for entry in parsed.entries:
            url = entry.get("link") or entry.get("guid") or entry.get("id")
            if url:
                links.append(url)
        if links:
            print(f"[+] RSS feed parsed: {len(links)} entries from {feed_url}")
        return links
    except Exception as e:
        print(f"[!] feedparser exception on {feed_url}: {e}")
        return []


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def discover_new_hackathons_async() -> List[str]:
    """
    Async version: uses Devpost JSON API for devpost.com feeds,
    RSS parsing for other feeds. Returns a de-duplicated list of URLs.
    """
    all_links: List[str] = []

    for feed_url in RSS_FEED_URLS:
        if "devpost.com" in feed_url:
            # Use the structured JSON API – much more reliable than scraping
            loop = asyncio.get_event_loop()
            links = await loop.run_in_executor(None, _devpost_api_links, 3)
            all_links.extend(links)
        else:
            # Try RSS for other sources
            rss_links = _rss_links_from_feed(feed_url)
            all_links.extend(rss_links)

    # De-duplicate while preserving order
    seen: set = set()
    unique: List[str] = []
    for link in all_links:
        if link not in seen:
            seen.add(link)
            unique.append(link)

    return unique


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
