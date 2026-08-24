# VIT Assist — Web Scraping & RAG Knowledge Base

Building a scraping pipeline for the VIT (Pune) website (`www.vit.edu`) as
the data foundation for a prospective-student chatbot.

## Project Structure
vit_assist/
├── webscrap.py # original single-page scraper (proof of concept)
├── webscrap_multi.py # multi-page crawler: sitemap + BFS discovery, boilerplate removal
├── pdf_pipeline.py # downloads + extracts text from VIT's fee/admission PDFs
├── scraped_pages/ # output: HTML pages as cleaned Markdown (git-ignored)
│ ├── via_sitemap/
│ └── via_bfs/
├── pdfs/ # output: downloaded PDF files (git-ignored)
├── pdfs_text/ # output: extracted PDF text (git-ignored)
├── requirements.txt
└── README.md



## Setup (do this once per machine)

```powershell
# 1. Create and activate a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install the Chromium browser Crawl4AI/Playwright needs
python -m playwright install chromium
```

If you ever see `ModuleNotFoundError` or a Playwright "Executable doesn't
exist" error, it usually means the packages installed into a *different*
Python than the one running the script. Fix by always using the full path
or an activated venv, e.g.:

```powershell
& "C:\Users\Local\Programs\Python\Python313\python.exe" -m pip install -r requirements.txt
```

## How to Run

### 1. Single-page test scraper
```powershell
python webscrap.py
```
Scrapes just the homepage, saves to `vit_website.md`. Good for a quick
sanity check that Crawl4AI + Chromium still work.

### 2. Multi-page crawler (main pipeline)
```powershell
python -u webscrap_multi.py
```
Runs two discovery strategies and saves cleaned Markdown:
- **Sitemap strategy** → `scraped_pages/via_sitemap/` — targeted, ranked by keywords (admission, fee, course, etc.)
- **BFS strategy** → `scraped_pages/via_bfs/` — follows internal links outward from the homepage

Key settings at the top of the file:
- `MAX_RELEVANT_PAGES` / `MAX_OTHER_PAGES` — sitemap crawl budget
- `BFS_MAX_PAGES` — BFS crawl budget
- `RELEVANT_KEYWORDS` — what counts as a "relevant" page

Runs sequentially (`crawler.arun()` in a loop), not `arun_many()` —
concurrent crawling caused a `MemoryError` on this machine. Keep it this
way unless that's fixed.

### 3. PDF pipeline
```powershell
python -u pdf_pipeline.py
```
Downloads VIT's fee/admission/eligibility PDFs directly via `requests`
(not the browser — direct navigation to PDFs crashes Crawl4AI) and
extracts text + tables with `pdfplumber`.
- Downloaded PDFs → `pdfs/`
- Extracted text → `pdfs_text/`

`MAX_PDFS` at the top controls the batch size — start small, raise once
you've checked output quality.

## Current Status

- [x] Single-page scraping working
- [x] Multi-page crawling (sitemap + BFS) working
- [x] Boilerplate/nav removal via `PruningContentFilter`
- [x] PDF-crash avoidance (excluded from browser crawl)
- [x] URL dedup (case/trailing-slash variants)
- [x] Memory-safe sequential crawling
- [ ] PDF download + text pipeline validated on real data
- [ ] Chunking
- [ ] Embeddings + vector DB
- [ ] RAG retrieval
- [ ] Chatbot integration

## Known Gotchas

- VIT's sitemap only works at `https://www.vit.edu/sitemap.xml` (must include `www`) and needs a browser-like `User-Agent` header, or requests get silently ignored.
- Direct PDF URLs crash Crawl4AI's browser navigation (`Page.goto: Download is starting`) — always filter PDFs out before the HTML crawl, handle them separately.
- `arun_many()` caused `MemoryError: Memory usage exceeded threshold` on this machine — use sequential `arun()` calls instead.