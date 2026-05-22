"""
crawler.py – High-concurrency async web scraper

Uses crawl4ai's AsyncWebCrawler with arun_many() for batched parallel crawls.
Semaphore capped at 10 concurrent requests to prevent rate-limiting.
All mock pages removed – production only.
"""

from __future__ import annotations

import re
import asyncio
import urllib.parse
from typing import List

from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Rotating User-Agent pool
# ---------------------------------------------------------------------------
USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

_ua_cycle_index = 0

def _next_user_agent() -> str:
    """Round-robin through the User-Agent pool."""
    global _ua_cycle_index
    ua = USER_AGENTS[_ua_cycle_index % len(USER_AGENTS)]
    _ua_cycle_index += 1
    return ua


# ---------------------------------------------------------------------------
# HTML → Markdown conversion
# ---------------------------------------------------------------------------

def html_to_markdown(html: str, base_url: str) -> str:
    """Strip boilerplate from HTML and return clean markdown (≤ 12 000 chars)."""
    soup = BeautifulSoup(html, "html.parser")
    for el in soup(["script", "style", "noscript", "svg", "iframe", "form",
                    "nav", "header", "footer", "aside"]):
        el.decompose()

    root = soup.find("main") or soup.find("article") or soup.body or soup
    chunks: List[str] = []

    def _recurse(elem):
        if elem.name is None:
            txt = str(elem).strip()
            if txt:
                chunks.append(txt)
            return
        tag = elem.name
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            chunks.append(f"\n{'#' * int(tag[1])} {elem.get_text().strip()}\n")
            return
        if tag == "p":
            chunks.append(f"\n{elem.get_text().strip()}\n")
            return
        if tag in ("ul", "ol"):
            chunks.append("\n")
            for idx, li in enumerate(elem.find_all("li", recursive=False)):
                prefix = f"{idx + 1}." if tag == "ol" else "-"
                chunks.append(f"{prefix} {li.get_text().strip()}")
            chunks.append("\n")
            return
        if tag == "a":
            href = elem.get("href", "")
            full = urllib.parse.urljoin(base_url, href) if href else ""
            text = elem.get_text().strip()
            if text and full and not full.startswith("javascript:"):
                chunks.append(f"[{text}]({full})")
            elif text:
                chunks.append(text)
            return
        for child in elem.children:
            if hasattr(child, "name"):
                _recurse(child)
            elif isinstance(child, str):
                t = child.strip()
                if t:
                    chunks.append(t)

    _recurse(root)
    full = " ".join(chunks)
    full = re.sub(r"\n\s*\n", "\n\n", full)
    full = re.sub(r" +", " ", full)
    return full[:12_000].strip()


# ---------------------------------------------------------------------------
# Single-URL crawl
# ---------------------------------------------------------------------------

async def _crawl4ai_fetch(url: str) -> str:
    """Crawl via crawl4ai (Playwright-based). Returns markdown or empty string."""
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

    browser_cfg = BrowserConfig(
        headless=True,
        verbose=False,
        user_agent=_next_user_agent(),
    )
    run_cfg = CrawlerRunConfig(
        word_count_threshold=10,
        only_text=False,
    )

    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        result = await crawler.arun(url=url, config=run_cfg)

    if result.success and result.html:
        return html_to_markdown(result.html, url)
    return ""


async def _httpx_fetch(url: str) -> str:
    """Simple HTTP fetch fallback using httpx + BeautifulSoup. No JS rendering."""
    import httpx
    import ssl

    try:
        async with httpx.AsyncClient(
            verify=False,
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": _next_user_agent(), "Accept": "text/html"},
        ) as client:
            resp = await client.get(url)
            if resp.status_code == 200 and resp.text:
                return html_to_markdown(resp.text, url)
    except Exception as e:
        print(f"[-] httpx fallback also failed for {url}: {e}")
    return ""


async def crawl_url(url: str) -> str:
    """
    Crawl a single URL. Tries crawl4ai (Playwright) first, falls back to
    simple httpx fetch if Playwright isn't available or fails.
    """
    print(f"[+] Crawling: {url}")
    try:
        result = await _crawl4ai_fetch(url)
        if result:
            return result
        print(f"[~] crawl4ai returned empty for {url}, trying httpx fallback...")
    except Exception as e:
        print(f"[~] crawl4ai unavailable ({type(e).__name__}), using httpx fallback for {url}")

    return await _httpx_fetch(url)


# ---------------------------------------------------------------------------
# Batch crawl with semaphore (arun_many equivalent via gather + semaphore)
# ---------------------------------------------------------------------------

async def crawl_urls(urls: List[str], concurrency: int = 10) -> List[str]:
    """
    Crawl a list of URLs concurrently. Uses a semaphore to cap parallelism at
    `concurrency` (default 10). Errors are isolated per URL – one failure never
    blocks the rest of the batch.

    Returns a list of markdown strings in the same order as `urls`.
    """
    semaphore = asyncio.Semaphore(concurrency)

    async def _sem_crawl(u: str) -> str:
        async with semaphore:
            try:
                return await crawl_url(u)
            except Exception as e:
                print(f"[-] Isolated crawl error for {u}: {e}")
                return ""

    return list(await asyncio.gather(*(_sem_crawl(u) for u in urls)))


# ---------------------------------------------------------------------------
# arun_many-style batch entry point (convenience wrapper)
# ---------------------------------------------------------------------------

async def arun_many(urls: List[str], semaphore_count: int = 10) -> List[str]:
    """
    Public alias matching crawl4ai's arun_many() semantics.
    Returns markdowns list aligned with input urls list.
    """
    return await crawl_urls(urls, concurrency=semaphore_count)
