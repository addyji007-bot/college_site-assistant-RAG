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
MAX_PDFS = 40  # raised now that ranking/dedup keeps the budget from being wasted
MAX_PER_FAMILY = 1  # keep only the most recent PDF per "document family" (see below)

RELEVANT_KEYWORDS = [
    "fee", "admission", "eligibil", "regulation",
    "prospectus", "brochure", "scholarship", "syllabus",
]
# Deprioritized: dated notices and per-year feedback forms are low value for
# a chatbot knowledge base (superseded, narrow-audience, or usually scanned
# images with no extractable text). Not excluded, just ranked lower.
LOW_PRIORITY_KEYWORDS = ["notice", "feedback", "circular"]


def extract_year(url: str) -> int:
    """Pull the most recent 4-digit year mentioned in the URL, so newer
    documents (2025 syllabus) outrank older ones (2018 syllabus) of the
    same type. Defaults to 0 (lowest priority) if no year found."""
    years = [int(y) for y in re.findall(r"20\d{2}", url)]
    return max(years) if years else 0


def extract_academic_year(url: str) -> str:
    """Best-effort academic-year label from the filename, e.g. '2024-25'.
    Purely for metadata/display -- so the chatbot can say 'per VIT's
    2024-25 hostel fee document' instead of implying it's current."""
    fname = url.split("/")[-1]
    m = re.search(r"(20\d{2})[-_](\d{2})(?!\d)", fname)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m2 = re.search(r"(?<!\d)(\d{2})[-_](\d{2})(?!\d)", fname)
    if m2:
        return f"20{m2.group(1)}-{m2.group(2)}"
    m3 = re.search(r"20\d{2}", fname)
    return m3.group(0) if m3 else None


# Document classification rules, checked in order -- first keyword match
# wins. This is the priority model from the project handoff doc: not
# every PDF deserves the same treatment, so classify BEFORE deciding
# whether to spend OCR effort on a zero-text PDF.
#   (document_type, priority, [keywords to match in the filename])
DOCUMENT_TYPE_RULES = [
    ("hostel_fee",           "HIGH",   ["hostel_fee", "hostel-fee"]),
    # feedback/notice/action_report checked BEFORE the generic "fee" match --
    # "fee" is a substring of "feedback", which silently misclassified
    # Student_Institute_Feedback_2023_24.pdf as a HIGH-priority fee document.
    ("feedback",             "LOW",    ["feedback", "stakeholder"]),
    ("notice",               "LOW",    ["notice", "circular"]),
    ("action_report",        "LOW",    ["action_report", "action-report"]),
    ("grievance_policy",     "MEDIUM", ["grievance", "ombudsman"]),
    ("institutional_policy", "MEDIUM", ["approval", "aicte", "eoa", "policy"]),
    ("fee_structure",        "HIGH",   ["fee"]),
    ("admission",            "HIGH",   ["admission"]),
    ("eligibility",          "HIGH",   ["eligibil"]),
    ("scholarship",          "HIGH",   ["scholarship"]),
    ("syllabus",             "HIGH",   ["syllabus", "syllabi"]),
    ("brochure",             "HIGH",   ["brochure", "prospectus"]),
    ("mandatory_disclosure", "HIGH",   ["mandatory-disclosure", "mandatory_disclosure"]),
    ("regulation",           "HIGH",   ["regulation"]),
]


def classify_document(url: str) -> dict:
    """Returns document_type, priority (HIGH/MEDIUM/LOW), and academic_year.
    Priority determines whether OCR is even attempted for zero-text PDFs --
    see decide_extraction_method() below."""
    fname = url.split("/")[-1].lower()
    doc_type, priority = "other", "MEDIUM"  # unknown docs -> flag for manual review, not auto-archived
    for name, pri, keywords in DOCUMENT_TYPE_RULES:
        if any(k in fname for k in keywords):
            doc_type, priority = name, pri
            break
    return {
        "document_type": doc_type,
        "priority": priority,
        "academic_year": extract_academic_year(url),
        "source_url": url,
    }


def document_family(url: str) -> str:
    """Normalize a filename by stripping year/date tokens, so different
    years of the 'same' document (e.g. Syllabus_CS_AY2023_24.pdf and
    Syllabus_CS_AY2024_25.pdf) collapse to one family. Only the newest
    member of each family is kept -- see MAX_PER_FAMILY."""
    fname = url.split("/")[-1].lower()
    fname = re.sub(r"20\d{2}", "", fname)          # strip 4-digit years
    fname = re.sub(r"[_\-]?\d{2}[_\-]\d{2}", "", fname)  # strip "24_25", "24-25"
    fname = re.sub(r"[^a-z]+", "_", fname).strip("_")
    return fname

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

    def score(url: str) -> tuple:
        u = url.lower()
        keyword_hit = any(k in u for k in RELEVANT_KEYWORDS)
        low_priority = any(k in u for k in LOW_PRIORITY_KEYWORDS)
        # Sort key: relevant keyword first, then not-low-priority, then newest year
        return (keyword_hit, not low_priority, extract_year(url))

    pdf_urls.sort(key=score, reverse=True)

    # Dedup by document family, keeping only the most recent (list is
    # already sorted newest-first within matching scores).
    seen_families = {}
    deduped = []
    dropped = 0
    for u in pdf_urls:
        fam = document_family(u)
        if fam in seen_families and len(seen_families[fam]) >= MAX_PER_FAMILY:
            dropped += 1
            continue
        seen_families.setdefault(fam, []).append(u)
        deduped.append(u)

    if dropped:
        print(f"[pdf] Dropped {dropped} older/duplicate-family PDFs "
              f"(keeping newest {MAX_PER_FAMILY} per document type)")

    relevant_count = sum(1 for u in deduped if any(k in u.lower() for k in RELEVANT_KEYWORDS))
    print(f"[pdf] {relevant_count} PDFs matched relevance keywords (fee/admission/etc)")

    return deduped


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

def extract_pdf_text_only(pdf_path: Path) -> str:
    """pdfplumber text + table extraction. No OCR fallback here --
    that decision belongs to decide_extraction_method(), gated by
    document priority, not applied blindly to every empty result."""
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


def decide_extraction_method(text: str, priority: str, pdf_path: Path) -> tuple:
    """Given the plain-text extraction result and the document's priority
    tier, decide what (if anything) to do next. Returns (final_text, method).

    HIGH priority + empty text   -> attempt OCR now
    MEDIUM priority + empty text -> flag for manual review, don't auto-OCR
    LOW priority + empty text    -> archive raw PDF only, skip entirely
    Non-empty text               -> keep it, no OCR needed
    """
    if len(text.strip()) >= 20:
        return text, "text"

    if priority == "HIGH":
        ocr_text = extract_pdf_text_via_ocr(pdf_path)
        return (ocr_text, "ocr") if ocr_text.strip() else ("", "ocr_failed")

    if priority == "MEDIUM":
        print(f"[pdf]   {pdf_path.name}: empty text, MEDIUM priority -- "
              f"needs manual review before OCR (not run automatically)")
        return "", "needs_manual_review"

    # LOW priority
    print(f"[pdf]   {pdf_path.name}: empty text, LOW priority -- archived raw PDF only, not processed")
    return "", "archived_only"


def extract_pdf_text_via_ocr(pdf_path: Path) -> str:
    """OCR fallback for scanned/image-only PDFs. Requires:
      pip install pytesseract pdf2image
    PLUS two system binaries that pip can't install for you:
      - Poppler (for pdf2image)   -> https://github.com/oschwartz10612/poppler-windows/releases
      - Tesseract-OCR             -> https://github.com/UB-Mannheim/tesseract/wiki
    Both need their install folder added to your Windows PATH.
    If either is missing this just prints a note and returns "" -- it
    does not crash the rest of the pipeline.
    """
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        print(f"[pdf]   OCR skipped for {pdf_path.name} -- "
              f"run: pip install pytesseract pdf2image")
        return ""

    try:
        images = convert_from_path(str(pdf_path))
    except Exception as e:
        print(f"[pdf]   OCR skipped for {pdf_path.name} -- "
              f"Poppler not found or not on PATH ({e})")
        return ""

    try:
        parts = []
        for i, image in enumerate(images):
            text = pytesseract.image_to_string(image)
            if text.strip():
                parts.append(f"--- Page {i + 1} (OCR) ---\n{text.strip()}")
        if parts:
            print(f"[pdf]   OCR recovered text from {pdf_path.name}")
        return "\n\n".join(parts)
    except Exception as e:
        print(f"[pdf]   OCR failed for {pdf_path.name} -- "
              f"Tesseract not found or not on PATH ({e})")
        return ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import json

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_DIR.mkdir(parents=True, exist_ok=True)

    urls = fetch_pdf_urls()[:MAX_PDFS]
    if not urls:
        print("[pdf] No PDF URLs found.")
        return

    print(f"[pdf] Processing {len(urls)} PDFs...\n")

    all_metadata = []
    for i, url in enumerate(urls):
        fname_base = re.sub(r"[^a-zA-Z0-9]+", "_", url.split("/")[-1])[:80]
        pdf_path = PDF_DIR / f"{i:02d}_{fname_base}"
        text_path = TEXT_DIR / f"{i:02d}_{fname_base}.txt"

        meta = classify_document(url)
        print(f"[pdf] {i + 1}/{len(urls)}: {url}")
        print(f"[pdf]   classified as: {meta['document_type']} "
              f"(priority={meta['priority']}, year={meta['academic_year']})")

        ok = download_pdf(url, pdf_path)
        if not ok:
            meta.update(extraction_method="download_failed", chars=0,
                        local_pdf=None, local_text=None)
            all_metadata.append(meta)
            continue

        raw_text = extract_pdf_text_only(pdf_path)
        final_text, method = decide_extraction_method(raw_text, meta["priority"], pdf_path)

        if final_text.strip():
            text_path.write_text(final_text, encoding="utf-8")
            local_text = str(text_path)
        else:
            local_text = None  # nothing worth saving as text -- PDF itself is still archived

        meta.update(
            extraction_method=method,
            chars=len(final_text),
            local_pdf=str(pdf_path),
            local_text=local_text,
        )
        all_metadata.append(meta)
        print(f"[pdf]   method={method}, {len(final_text)} chars -> "
              f"{text_path.name if local_text else '(not saved -- see method)'}\n")

        time.sleep(0.5)  # be polite to VIT's server

    # The metadata/priority layer the project handoff doc called for --
    # this is what lets you (or a later chunking/RAG step) filter by
    # priority, document_type, or academic_year instead of treating
    # every PDF as equally trustworthy/current.
    metadata_path = TEXT_DIR / "metadata.json"
    metadata_path.write_text(json.dumps(all_metadata, indent=2), encoding="utf-8")

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    by_method = {}
    for m in all_metadata:
        by_method.setdefault(m["extraction_method"], []).append(m)

    for method, items in sorted(by_method.items()):
        print(f"{method}: {len(items)}")
    print()

    for m in all_metadata:
        print(f"  [{m['priority']:<6}] [{m['extraction_method']:<20}] "
              f"{m['chars']:>6} chars  {m['document_type']:<22} {m['source_url']}")

    print(f"\nFull metadata written to {metadata_path}")
    if by_method.get("needs_manual_review"):
        print(f"\n{len(by_method['needs_manual_review'])} MEDIUM-priority PDFs need manual review "
              f"before deciding on OCR (see metadata.json, extraction_method='needs_manual_review')")


if __name__ == "__main__":
    main()