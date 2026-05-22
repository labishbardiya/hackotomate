# 🌊 Hackotomate — Autonomous Hackathon Aggregator

An AI-powered web aggregator that autonomously discovers hackathons from public directories, extracts structured metadata via **NVIDIA NIM LLM**, dynamically classifies them into emerging taxonomy tracks, and displays everything on a premium glassmorphic **Ocean Terminal** dashboard.

### 🔗 [Live Demo → hackotomate.onrender.com](https://hackotomate.onrender.com)

---

## ✨ Features

- **Autonomous Discovery** — Fetches live hackathon listings from the Devpost JSON API (supports multiple feed sources)
- **AI-Powered Extraction** — Uses NVIDIA NIM (`nvidia/llama-3.3-nemotron-super-49b-v1`) for structured data extraction from crawled pages
- **Dynamic Taxonomy** — Self-organizing classification engine that creates and manages track categories in real-time
- **Deep Crawling** — Crawl4AI + Playwright for full JavaScript-rendered page extraction
- **Real-Time Pipeline Logs** — Live streaming ingestion monitor with glowing terminal aesthetics
- **Premium UI** — Glassmorphic design with animated gradients, touch-scrollable cards, and responsive mobile layout
- **PostgreSQL Persistence** — Production-grade storage via Supabase with connection pooling

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (SPA)                        │
│   index.html  ·  style.css  ·  app.js                   │
│   Glassmorphic UI · Track Filters · Pipeline Monitor    │
└───────────────────────┬─────────────────────────────────┘
                        │ REST API
┌───────────────────────▼─────────────────────────────────┐
│                  FastAPI Backend                         │
│                                                         │
│  server.py ──── /api/hackathons · /api/tracks           │
│                 /api/pipeline/run · /api/pipeline/reset  │
│                                                         │
│  pipeline.py ── Batch ingestion orchestrator             │
│  discovery.py ─ Devpost API + RSS feed harvester         │
│  crawler.py ─── Crawl4AI async batch crawler             │
│  classifier.py─ NVIDIA NIM taxonomy classifier           │
│  database.py ── PostgreSQL (Supabase) connection pool    │
│  schema.py ──── Pydantic models                          │
└───────────────────────┬─────────────────────────────────┘
                        │
          ┌─────────────▼──────────────┐
          │   Supabase PostgreSQL DB   │
          │   dynamic_tracks           │
          │   ocean_hackathons         │
          └────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- A Supabase project (free tier works) — [supabase.com](https://supabase.com)
- NVIDIA NIM API key — [build.nvidia.com](https://build.nvidia.com)

### 1. Clone & Setup

```bash
git clone https://github.com/yourusername/hackotomate.git
cd hackotomate

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (needed for Crawl4AI)
playwright install
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

| Variable | Description |
|---|---|
| `SUPABASE_URL` | PostgreSQL connection string from Supabase |
| `NVIDIA_API_KEY` | API key from NVIDIA Build |
| `ADMIN_SECRET_KEY` | Optional — protects pipeline endpoints |
| `DISCOVERY_FEEDS` | Comma-separated feed URLs (default: Devpost) |

### 3. Launch

```bash
uvicorn backend.server:app --host 0.0.0.0 --port 8000
```

Open **[http://localhost:8000](http://localhost:8000)** in your browser.

---

## 🔧 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/hackathons` | List all hackathons (optional `?track=` filter) |
| `GET` | `/api/tracks` | List all dynamic taxonomy tracks |
| `GET` | `/api/pipeline/run` | Stream the ingestion pipeline (requires `x-admin-key` header if `ADMIN_SECRET_KEY` is set) |
| `POST` | `/api/pipeline/reset` | Drop & recreate tables (requires `x-admin-key` header) |

---

## 🎯 How It Works

1. **Discovery** — Queries the Devpost JSON API to discover open hackathons
2. **Crawling** — Batch-crawls each hackathon page using Crawl4AI with Playwright
3. **Extraction** — Sends page content to NVIDIA NIM for structured data extraction (name, dates, prizes, organizer, etc.)
4. **Classification** — NIM analyzes event details against existing taxonomy tracks and either matches or creates new ones
5. **Storage** — Upserts records into Supabase PostgreSQL with conflict resolution
6. **Display** — Frontend fetches from the API and renders cards with dynamic track filters

---

## 📁 Project Structure

```
hackotomate/
├── .env.example          # Environment variable template
├── .gitignore            # Git ignore rules
├── requirements.txt      # Python dependencies
├── README.md             # This file
├── backend/
│   ├── server.py         # FastAPI application & routes
│   ├── pipeline.py       # Batch ingestion orchestrator
│   ├── discovery.py      # URL harvester (Devpost API + RSS)
│   ├── crawler.py        # Crawl4AI async batch crawler
│   ├── classifier.py     # NVIDIA NIM taxonomy classifier
│   ├── database.py       # PostgreSQL connection pool
│   ├── schema.py         # Pydantic data models
│   └── requirements.txt  # Backend-specific deps
└── frontend/
    ├── index.html        # Main HTML shell
    ├── style.css         # Glassmorphic Ocean theme
    └── app.js            # SPA logic & API integration
```

---

## 📜 License

MIT License — see [LICENSE](LICENSE) for details.
