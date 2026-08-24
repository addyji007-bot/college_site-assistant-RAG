"""
pdf_pipeline.py

Phase B of the VIT knowledge-base project: collects the PDFs that
webscrap_multi.py intentionally skips (fee structures, admission
documents, notices, regulations) via direct HTTP download instead of
browser navigation, then extracts their text.

Pipeline:
  1. Re-fetch sitemap.xml, this time pulling OUT the .pdf URLs
     (webscrap_multi.py does the opposite -- keeps HTML, drops PDFs).
  2. Rank PDFs by relevance keywords (fee, admission, eligibility, etc.)
     so the ones that matter most for the chatbot come first.
  3. Download each PDF with `requests` (streamed, no browser involved --
     this is what avoids the Page.goto "Download is starting" crash).
  4. Extract text with pdfplumber (handles fee-structure tables better
     than plain pypdf text extraction).
  5. Save raw PDFs to pdfs/ and extracted text to pdfs_text/.

Run with your project's Python:
    & "C:\\Users\\Aditya Gupta\\AppData\\Local\\Programs\\Python\\Python313\\python.exe" -u "pdf_pipeline.py"

Requires: pip install pdfplumber
"""

import re
import time
from pathlib import Path
from xml.etree import ElementTree

import requests
import pdfplumber

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SITEMAP_URL = "https://www.vit.edu/sitemap.xml"
MAX_PDFS = 25  # quick test batch -- raise once validated

RELEVANT_KEYWORDS = [
    "fee", "admission", "eligibil", "regulation", "notice",
    "prospectus", "brochure", "scholarship", "syllabus", "circular",
]

PDF_DIR = Path("pdfs")
TEXT_DIR = Path("pdfs_text")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


# ---------------------------------------------------------------------------
# Step 1+2: Find and rank PDF URLs from the sitemap
# ---------------------------------------------------------------------------

def fetch_pdf_urls() -> list[str]:
    print("[pdf] Fetching sitemap...")
    resp = requests.get(SITEMAP_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    root = ElementTree.fromstring(resp.content)
    ns = {"sm": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}
    loc_tag = f"{{{ns['sm']}}}loc" if ns else "loc"

    all_urls = [el.text.strip() for el in root.iter(loc_tag) if el.text]
    pdf_urls = [u for u in all_urls if re.search(r"\.pdf(?:$|\?)", u, re.IGNORECASE)]

    print(f"[pdf] {len(all_urls)} total sitemap URLs, {len(pdf_urls)} are PDFs")

    relevant = [u for u in pdf_urls if any(k in u.lower() for k in RELEVANT_KEYWORDS)]
    others = [u for u in pdf_urls if u not in relevant]
    print(f"[pdf] {len(relevant)} PDFs matched relevance keywords (fee/admission/etc)")

    return relevant + others


# ---------------------------------------------------------------------------
# Step 3: Direct download (no browser)
# ---------------------------------------------------------------------------

def download_pdf(url: str, dest: Path) -> bool:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30, stream=True)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "pdf" not in content_type.lower() and not url.lower().endswith(".pdf"):
            print(f"[pdf] SKIP (not a PDF response): {url} -> {content_type}")
            return False

        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"[pdf] DOWNLOAD FAILED: {url} -> {e}")
        return False


# ---------------------------------------------------------------------------
# Step 4: Text extraction
# ---------------------------------------------------------------------------

def extract_pdf_text(pdf_path: Path) -> str:
    """Extract text page by page, and any tables (fee sheets are usually
    tabular), rendering tables as simple pipe-separated rows inline."""
    parts = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                if text.strip():
                    parts.append(f"--- Page {i + 1} ---\n{text.strip()}")

                tables = page.extract_tables()
                for t_idx, table in enumerate(tables):
                    rows = [
                        " | ".join(cell or "" for cell in row)
                        for row in table
                        if row
                    ]
                    if rows:
                        parts.append(
                            f"--- Page {i + 1} Table {t_idx + 1} ---\n" + "\n".join(rows)
                        )
    except Exception as e:
        return f"[extraction error: {e}]"

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_DIR.mkdir(parents=True, exist_ok=True)

    urls = fetch_pdf_urls()[:MAX_PDFS]
    if not urls:
        print("[pdf] No PDF URLs found.")
        return

    print(f"[pdf] Processing {len(urls)} PDFs...\n")

    summary = []
    for i, url in enumerate(urls):
        fname_base = re.sub(r"[^a-zA-Z0-9]+", "_", url.split("/")[-1])[:80]
        pdf_path = PDF_DIR / f"{i:02d}_{fname_base}"
        text_path = TEXT_DIR / f"{i:02d}_{fname_base}.txt"

        print(f"[pdf] {i + 1}/{len(urls)}: {url}")
        ok = download_pdf(url, pdf_path)
        if not ok:
            summary.append((url, "download_failed", 0))
            continue

        text = extract_pdf_text(pdf_path)
        text_path.write_text(text, encoding="utf-8")
        summary.append((url, "ok", len(text)))
        print(f"[pdf]   saved {pdf_path.name}, extracted {len(text)} chars -> {text_path.name}\n")

        time.sleep(0.5)  # be polite to VIT's server

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    ok_count = sum(1 for _, status, _ in summary if status == "ok")
    print(f"Downloaded + extracted: {ok_count}/{len(summary)}")
    for url, status, chars in summary:
        marker = "OK" if status == "ok" else "FAIL"
        print(f"  [{marker}] {chars:>6} chars  {url}")


if __name__ == "__main__":
    main()
