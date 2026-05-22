"""
classifier.py – Dynamic taxonomy classifier

Uses NVIDIA NIM (nvidia/llama-3.3-nemotron-super-49b-v1) for semantic track
classification. Falls back to keyword-rule classifier only if NVIDIA_API_KEY
is absent. All SQLite ? placeholders replaced with PostgreSQL %s.
sanitize_slug() performs DB cross-reference deduplication before creating tracks.
"""

from __future__ import annotations

import os
import re
import json
from openai import OpenAI
from backend.schema import HackathonDetails, TaxonomyDecision
from backend.database import get_db_connection, release_db_connection

# ---------------------------------------------------------------------------
# NVIDIA NIM client initialization
# ---------------------------------------------------------------------------
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
HAS_NIM = bool(NVIDIA_API_KEY and not NVIDIA_API_KEY.startswith("nvapi-your-nvidia"))

if HAS_NIM:
    nim_client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=NVIDIA_API_KEY,
    )
    print("[+] NVIDIA NIM client initialized: nvidia/llama-3.3-nemotron-super-49b-v1")
else:
    print("[!] NVIDIA_API_KEY not set. Using keyword rule-based fallback classifier.")
    nim_client = None


# ---------------------------------------------------------------------------
# Slug sanitizer
# ---------------------------------------------------------------------------

def sanitize_slug(slug_str: str) -> str:
    """
    Forces any string into a lowercase, hyphen-separated, alphanumeric-only slug.
    Performs no DB check here – use classify_and_register_hackathon for dedup.
    """
    slug = slug_str.strip().lower()
    slug = re.sub(r"[\s_\-]+", "-", slug)
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    return slug.strip("-")


# ---------------------------------------------------------------------------
# Keyword-rule fallback classifier
# ---------------------------------------------------------------------------

def _keyword_classify(details: HackathonDetails, existing_tracks: list) -> TaxonomyDecision:
    """
    Rule-based classifier. Matches against existing track slugs; creates a new
    track if no existing slug matches with at least 2 keyword hits.
    """
    text = (
        details.name + " " + details.description_summary + " " + " ".join(details.tags)
    ).lower()

    rules = {
        "generative-agents": ["agent", "llm", "gpt", "prompt", "nemotron", "chatbot", "generative", "ai"],
        "decentralized-networks": ["solana", "web3", "crypto", "blockchain", "ethereum", "contract", "defi"],
        "synthetic-biology": ["bio", "genom", "healthcare", "protein", "medical", "clinic", "dna"],
        "climate-solutions": ["climate", "green", "carbon", "eco", "energy", "grid", "sustainability"],
    }

    existing_slugs = {t["slug"] for t in existing_tracks}
    best_slug = "NONE"
    best_score = 0

    for slug, keywords in rules.items():
        if slug in existing_slugs:
            score = sum(1 for kw in keywords if kw in text)
            if score >= 2 and score > best_score:
                best_score = score
                best_slug = slug

    if best_slug != "NONE":
        return TaxonomyDecision(
            is_new_track_required=False,
            matched_track_slug=best_slug,
            suggested_new_track_name="",
            suggested_new_track_slug="",
            suggested_new_track_summary="",
        )

    # Suggest a new track
    if "quantum" in text or "physics" in text:
        name, summary = "Quantum Computing", "Qubit algorithms, quantum cryptography, and supercomputing."
    elif "space" in text or "orbit" in text or "satellite" in text:
        name, summary = "AstroTech & Orbitals", "Telemetry, aerospace hardware, and satellite systems."
    elif "cyber" in text or "security" in text or "penetration" in text:
        name, summary = "Cybersecurity Defense", "Zero-trust protocols, pen-testing, and threat detection."
    elif "game" in text or "unreal" in text or "unity" in text or "metaverse" in text:
        name, summary = "Immersive Gaming", "Game engines, multiplayer netcode, and VR interactions."
    elif "robot" in text or "iot" in text or "hardware" in text:
        name, summary = "Robotics & IoT", "Embedded systems, robotics, and connected hardware."
    else:
        name, summary = "Alternative Frontiers", "Emerging technology across niche open-source domains."

    return TaxonomyDecision(
        is_new_track_required=True,
        matched_track_slug="NONE",
        suggested_new_track_name=name,
        suggested_new_track_slug=sanitize_slug(name),
        suggested_new_track_summary=summary,
    )


# ---------------------------------------------------------------------------
# Core classification & registration function
# ---------------------------------------------------------------------------

def classify_and_register_hackathon(details: HackathonDetails) -> str:
    """
    Evaluates HackathonDetails against existing dynamic_tracks in the DB.
    1. Queries existing tracks.
    2. Calls NVIDIA NIM (if available) for structured TaxonomyDecision.
    3. Falls back to keyword classifier.
    4. Performs strict slug deduplication before inserting new tracks.
    5. Returns the finalized track slug.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Fetch all existing tracks for context
        cursor.execute("SELECT slug, display_name, summary FROM dynamic_tracks;")
        existing_tracks = [
            {"slug": row[0], "display_name": row[1], "summary": row[2]}
            for row in cursor.fetchall()
        ]

        decision: TaxonomyDecision | None = None

        # ── NIM classification ─────────────────────────────────────────────
        if HAS_NIM:
            print("[+] Calling NVIDIA NIM taxonomy classifier...")
            tracks_ctx = json.dumps(existing_tracks, indent=2)
            event_ctx = (
                f"Name: {details.name}\n"
                f"Organizer: {details.organizer}\n"
                f"Summary: {details.description_summary}\n"
                f"Tags: {', '.join(details.tags)}"
            )
            prompt = (
                "You are a dynamic taxonomy classifier for the Ocean Hackathons aggregator.\n\n"
                f"[EXISTING TRACKS]\n{tracks_ctx}\n\n"
                f"[NEW EVENT]\n{event_ctx}\n\n"
                "Decide: does this event fit an existing track (matched_track_slug = exact slug, "
                "is_new_track_required = false) or does it need a new track "
                "(is_new_track_required = true, suggest name/slug/summary)?"
            )
            try:
                completion = nim_client.beta.chat.completions.parse(
                    model="nvidia/llama-3.3-nemotron-super-49b-v1",
                    messages=[
                        {"role": "system", "content": "You are a professional taxonomy architect. Respond with structured JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    response_format=TaxonomyDecision,
                )
                decision = completion.choices[0].message.parsed
                print(f"[+] NIM taxonomy decision: {decision}")
            except Exception as e:
                print(f"[-] NIM taxonomy call failed: {e}. Using keyword fallback.")
                decision = None

        # ── Keyword fallback ───────────────────────────────────────────────
        if decision is None:
            decision = _keyword_classify(details, existing_tracks)
            print(f"[~] Keyword classifier decision: {decision}")

        # ── Apply decision ─────────────────────────────────────────────────
        if decision.is_new_track_required:
            raw_slug = decision.suggested_new_track_slug or sanitize_slug(decision.suggested_new_track_name)
            final_slug = sanitize_slug(raw_slug) or "niche-innovation"

            print(f"[+] Evaluating new track slug: '{final_slug}'")

            # Strict deduplication: check DB before inserting
            cursor.execute(
                "SELECT slug FROM dynamic_tracks WHERE slug = %s;", (final_slug,)
            )
            if cursor.fetchone():
                print(f"[~] Slug '{final_slug}' already exists. Reusing.")
            else:
                display_name = decision.suggested_new_track_name or final_slug.replace("-", " ").title()
                summary = decision.suggested_new_track_summary or f"Dynamic aggregate for {display_name} hackathons."
                print(f"[+] Creating new track: '{display_name}' ({final_slug})")
                cursor.execute(
                    """
                    INSERT INTO dynamic_tracks (slug, display_name, summary)
                    VALUES (%s, %s, %s);
                    """,
                    (final_slug, display_name, summary),
                )
                conn.commit()
        else:
            final_slug = decision.matched_track_slug
            # Guard against stale slug references
            cursor.execute(
                "SELECT slug FROM dynamic_tracks WHERE slug = %s;", (final_slug,)
            )
            if not cursor.fetchone():
                print(f"[!] Matched slug '{final_slug}' not found in DB. Auto-creating track.")
                display_name = final_slug.replace("-", " ").title()
                cursor.execute(
                    """
                    INSERT INTO dynamic_tracks (slug, display_name, summary)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (slug) DO NOTHING;
                    """,
                    (final_slug, display_name, f"Auto-created track for {display_name} hackathons."),
                )
                conn.commit()

        return final_slug

    finally:
        release_db_connection(conn)
