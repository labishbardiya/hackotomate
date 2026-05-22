"""
pipeline.py – Production batch ingestion engine

Architecture:
  1. Discover URLs (RSS / Deep-Crawl via discovery.py)
  2. Batch-crawl with arun_many (semaphore=10)
  3. Batch-classify with asyncio.gather via NVIDIA NIM (batch size 5)
  4. Upsert each record to Supabase PostgreSQL
  5. Yield every status token as a line for real-time StreamingResponse

No mock data, no SQLite, no fallback seeding.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from typing import AsyncGenerator, List, Optional

from backend.crawler import arun_many
from backend.schema import HackathonDetails
from backend.classifier import classify_and_register_hackathon, HAS_NIM, nim_client
from backend.database import get_db_connection, release_db_connection
from backend.discovery import discover_new_hackathons_async

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BATCH_SIZE = 5          # Number of URLs classified concurrently via NIM
CRAWL_CONCURRENCY = 10  # Semaphore count for crawler


# ---------------------------------------------------------------------------
# Lightweight heuristic extractor (only used when NIM is unavailable)
# ---------------------------------------------------------------------------

def _heuristic_extraction(markdown_text: str, url: str) -> HackathonDetails:
    """
    Minimal rule-based extractor. Parses whatever structure is available from
    the cleaned markdown. Never returns mock data – always real scraped content.
    """
    lines = [l.strip() for l in markdown_text.split("\n") if l.strip()]
    title = lines[0][:120] if lines else "Unnamed Hackathon"
    if title.startswith("#"):
        title = title.lstrip("#").strip()

    # Attempt to find dates via regex (YYYY-MM-DD or Month DD, YYYY)
    date_pattern = re.compile(
        r"\b(\d{4}-\d{2}-\d{2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4})\b",
        re.IGNORECASE,
    )
    found_dates = date_pattern.findall(markdown_text)

    def _safe_date(idx: int) -> Optional[str]:
        if idx < len(found_dates):
            raw = found_dates[idx]
            for fmt in ("%Y-%m-%d", "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
                try:
                    return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    continue
        return None

    # Prize heuristic – look for $ amounts
    prize_match = re.search(r"\$[\d,]+(?:\s*(?:USD|usd))?(?:\s+[\w\s]+)?", markdown_text)
    prize_text = prize_match.group(0).strip() if prize_match else "See listing"

    # Simple organizer extraction – look for "by <Name>" or "hosted by"
    org_match = re.search(r"(?:hosted|organized|presented)\s+by\s+([A-Z][^\.\n]{3,50})", markdown_text, re.IGNORECASE)
    organizer = org_match.group(1).strip() if org_match else "Unknown Organizer"

    return HackathonDetails(
        name=title,
        organizer=organizer,
        description_summary=(markdown_text[:300] + "…") if len(markdown_text) > 300 else markdown_text,
        start_date=_safe_date(0),
        end_date=_safe_date(1),
        registration_deadline=_safe_date(2),
        prize_pool=prize_text,
        tags=["hackathon"],
        registration_url=url,
    )


# ---------------------------------------------------------------------------
# NIM structured extraction (async, isolated)
# ---------------------------------------------------------------------------

async def _nim_extract(markdown_text: str, url: str) -> Optional[HackathonDetails]:
    """
    Call NVIDIA NIM for structured extraction. Returns None on any failure
    so the pipeline can fall back gracefully.
    """
    if not HAS_NIM:
        return None
    try:
        loop = asyncio.get_event_loop()
        completion = await loop.run_in_executor(
            None,
            lambda: nim_client.beta.chat.completions.parse(
                model="nvidia/llama-3.3-nemotron-super-49b-v1",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a precise structured data extraction agent. "
                            "Extract hackathon event details from the provided markdown text. "
                            "Return only the structured JSON matching the schema."
                        ),
                    },
                    {"role": "user", "content": markdown_text[:8000]},
                ],
                response_format=HackathonDetails,
            ),
        )
        return completion.choices[0].message.parsed
    except Exception as e:
        print(f"[!] NIM extraction error for {url}: {e}")
        return None


# ---------------------------------------------------------------------------
# DB upsert (PostgreSQL %s placeholders)
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def _sanitize_date(val: str | None) -> str | None:
    """Return val only if it's a valid YYYY-MM-DD string, else None."""
    if val and _DATE_RE.match(val.strip()):
        return val.strip()
    return None


def _db_upsert(details: HackathonDetails, track_slug: str) -> str:
    """Insert or update hackathon record. Returns success/error message."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Sanitize dates – NIM often returns "Not Provided", "Unknown", etc.
        start_date = _sanitize_date(details.start_date)
        end_date = _sanitize_date(details.end_date)
        reg_deadline = _sanitize_date(details.registration_deadline)

        cursor.execute(
            """
            INSERT INTO ocean_hackathons (
                name, organizer, description_summary, track_slug, registration_url,
                start_date, end_date, registration_deadline, prize_pool, tags
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (registration_url)
            DO UPDATE SET
                name                = EXCLUDED.name,
                organizer           = EXCLUDED.organizer,
                description_summary = EXCLUDED.description_summary,
                track_slug          = EXCLUDED.track_slug,
                start_date          = EXCLUDED.start_date,
                end_date            = EXCLUDED.end_date,
                registration_deadline = EXCLUDED.registration_deadline,
                prize_pool          = EXCLUDED.prize_pool,
                tags                = EXCLUDED.tags;
            """,
            (
                details.name,
                details.organizer,
                details.description_summary,
                track_slug,
                details.registration_url,
                start_date,
                end_date,
                reg_deadline,
                details.prize_pool,
                json.dumps(details.tags),
            ),
        )
        conn.commit()
        return f"[+] DB SYNC OK: '{details.name}' → track '{track_slug}'"
    except Exception as e:
        conn.rollback()
        return f"[-] DB SYNC FAILED for '{details.name}': {e}"
    finally:
        release_db_connection(conn)


# ---------------------------------------------------------------------------
# Process one URL (crawl → extract → classify → upsert)
# ---------------------------------------------------------------------------

async def _process_one(url: str, markdown: str) -> List[str]:
    """
    Full lifecycle for a single URL. Returns a list of log lines.
    Errors are caught and isolated – never aborts the stream.
    """
    logs: List[str] = []
    if not markdown:
        logs.append(f"[-] Empty content returned for {url}. Skipping.")
        return logs

    logs.append(f"[+] Content extracted ({len(markdown)} chars). Dispatching to NVIDIA NIM...")

    # NIM extraction
    details = await _nim_extract(markdown, url)
    if details:
        logs.append(f"[+] NIM structured parse succeeded: '{details.name}'")
    else:
        logs.append("[~] NIM unavailable or timed out. Using heuristic extractor.")
        details = _heuristic_extraction(markdown, url)
        logs.append(f"[+] Heuristic extraction mapped: '{details.name}'")

    # Always use the original crawled URL as registration_url
    # NIM often returns garbage like "null", instructions, or partial URLs
    details.registration_url = url

    # Taxonomy classification (sync, wraps DB call)
    logs.append("[+] Analyzing semantic taxonomy boundaries...")
    try:
        loop = asyncio.get_event_loop()
        track_slug = await loop.run_in_executor(None, classify_and_register_hackathon, details)
        logs.append(f"[+] Classified under track slug: '{track_slug}'")
    except Exception as e:
        logs.append(f"[-] Taxonomy classification error: {e}. Using fallback slug 'uncategorized'.")
        track_slug = "uncategorized"

    # DB upsert
    logs.append("[+] Synchronizing record to Supabase PostgreSQL...")
    db_msg = await asyncio.get_event_loop().run_in_executor(None, _db_upsert, details, track_slug)
    logs.append(db_msg)

    return logs


# ---------------------------------------------------------------------------
# Main streaming pipeline generator
# ---------------------------------------------------------------------------

async def run_pipeline_generator(single_url: Optional[str] = None) -> AsyncGenerator[str, None]:
    """
    Async generator that yields log lines in real time for FastAPI StreamingResponse.
    Processes URLs in batches of BATCH_SIZE through NIM concurrently.
    """
    yield "[*] OCEAN INGESTION ENGINE – STARTING\n"

    # ── Step 1: URL Discovery ──────────────────────────────────────────────
    if single_url:
        queue = [single_url]
        yield f"[+] Single URL mode: {single_url}\n"
    else:
        yield "[+] Running automated feed discovery...\n"
        try:
            queue = await discover_new_hackathons_async()
        except Exception as e:
            yield f"[-] Discovery failed: {e}\n"
            queue = []
        yield f"[+] Discovered {len(queue)} target URLs.\n"

    if not queue:
        yield "[-] No URLs to process. Pipeline terminated.\n"
        return

    # ── Step 2: Batch Crawl ────────────────────────────────────────────────
    yield f"[+] Launching batch crawler (concurrency={CRAWL_CONCURRENCY})...\n"
    yield f"[*] Crawling {len(queue)} pages via crawl4ai arun_many...\n"

    try:
        markdowns: List[str] = await arun_many(queue, semaphore_count=CRAWL_CONCURRENCY)
    except Exception as e:
        yield f"[-] Batch crawl fatal error: {e}\n"
        return

    yield f"[+] Crawl complete. {sum(1 for m in markdowns if m)} pages yielded content.\n"

    # ── Step 3: Batch Process (classify + upsert) ──────────────────────────
    total = len(queue)
    processed = 0

    for batch_start in range(0, total, BATCH_SIZE):
        batch_urls = queue[batch_start:batch_start + BATCH_SIZE]
        batch_mds  = markdowns[batch_start:batch_start + BATCH_SIZE]

        yield f"\n[*] ── BATCH [{batch_start + 1}–{min(batch_start + BATCH_SIZE, total)}/{total}] ──\n"
        yield f"[+] Dispatched batch to NVIDIA NIM ({len(batch_urls)} pages)...\n"

        tasks = [_process_one(u, md) for u, md in zip(batch_urls, batch_mds)]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(batch_results):
            url = batch_urls[i]
            yield f"[*] Processing: {url}\n"
            if isinstance(result, Exception):
                yield f"[-] Unhandled exception for {url}: {result}\n"
            else:
                for log_line in result:
                    yield f"{log_line}\n"
            processed += 1

    # ── Done ───────────────────────────────────────────────────────────────
    yield f"\n[+] ── PIPELINE COMPLETE: {processed}/{total} nodes processed ──\n"
