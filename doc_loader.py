"""
doc_loader.py

Loads documents from both scraping pipelines' output and returns them as
LangChain Document objects (page_content + metadata), ready for
text_splitter.py.

  - HTML markdown from webscrap_multi.py (scraped_pages/via_sitemap, via_bfs)
  - PDF text from pdf_pipeline.py (pdfs_text/)

Each Document's metadata:
  {
    "source_url": str,
    "source_type": "html" | "pdf",
    "document_type": str,   # "webpage", or pdf_pipeline's classification (fee_structure, syllabus, ...)
    "priority": "HIGH" | "MEDIUM" | "LOW",
    "academic_year": str,   # "unknown" if not applicable -- Chroma metadata can't store None
    "discovery_method": str,  # "sitemap", "bfs", or "pdf_pipeline"
  }

Run this file directly to sanity-check what it would load without
running the rest of the pipeline:
    python doc_loader.py
"""

import json
import hashlib
from pathlib import Path

from langchain_core.documents import Document

import config


def load_html_docs(folder: Path, source_label: str) -> list[Document]:
    """Load markdown pages + their metadata.json (url per file), written
    by webscrap_multi.py."""
    meta_path = folder / "metadata.json"
    if not meta_path.exists():
        print(f"[doc_loader] WARNING: no metadata.json in {folder} -- "
              f"re-run webscrap_multi.py to generate it. Skipping this folder.")
        return []

    meta_list = json.loads(meta_path.read_text(encoding="utf-8"))
    docs = []
    for entry in meta_list:
        fpath = folder / entry["file"]
        if not fpath.exists():
            continue
        text = fpath.read_text(encoding="utf-8")
        if not text.strip():
            continue
        docs.append(Document(
            page_content=text,
            metadata={
                "source_url": entry["source_url"],
                "source_type": "html",
                "document_type": "webpage",
                "priority": "HIGH",  # HTML pages were already keyword-filtered at crawl time
                "academic_year": "unknown",
                "discovery_method": source_label,
            },
        ))
    print(f"[doc_loader] Loaded {len(docs)} HTML docs from {folder}")
    return docs


def load_pdf_docs(folder: Path) -> list[Document]:
    """Load extracted PDF text + its metadata.json, written by pdf_pipeline.py.
    Only loads PDFs that actually have text (skips archived_only /
    needs_manual_review / download_failed / ocr_failed entries)."""
    meta_path = folder / "metadata.json"
    if not meta_path.exists():
        print(f"[doc_loader] WARNING: no metadata.json in {folder} -- "
              f"run pdf_pipeline.py first. Skipping PDFs.")
        return []

    meta_list = json.loads(meta_path.read_text(encoding="utf-8"))
    docs = []
    for entry in meta_list:
        if not entry.get("local_text"):
            continue
        fpath = Path(entry["local_text"])
        if not fpath.exists():
            continue
        text = fpath.read_text(encoding="utf-8")
        if not text.strip():
            continue
        docs.append(Document(
            page_content=text,
            metadata={
                "source_url": entry["source_url"],
                "source_type": "pdf",
                "document_type": entry["document_type"],
                "priority": entry["priority"],
                "academic_year": entry["academic_year"] or "unknown",
                "discovery_method": "pdf_pipeline",
            },
        ))
    print(f"[doc_loader] Loaded {len(docs)} PDF docs from {folder}")
    return docs


def dedup_by_content(docs: list[Document]) -> list[Document]:
    """The sitemap and BFS strategies can both reach the same page (e.g.
    /about/). Dedup by content hash so it isn't indexed twice."""
    seen_hashes = set()
    deduped = []
    for doc in docs:
        h = hashlib.md5(doc.page_content.encode("utf-8")).hexdigest()
        if h in seen_hashes:
            continue
        seen_hashes.add(h)
        deduped.append(doc)
    dropped = len(docs) - len(deduped)
    if dropped:
        print(f"[doc_loader] Dropped {dropped} duplicate-content docs (same page reached twice)")
    return deduped


def load_all_documents() -> list[Document]:
    """Main entry point: load everything, dedup, return the combined list."""
    docs = []
    docs += load_html_docs(config.SITEMAP_DIR, "sitemap")
    docs += load_html_docs(config.BFS_DIR, "bfs")
    docs += load_pdf_docs(config.PDF_TEXT_DIR)
    docs = dedup_by_content(docs)

    print(f"[doc_loader] Total documents loaded: {len(docs)}")
    by_priority = {}
    for d in docs:
        by_priority.setdefault(d.metadata["priority"], 0)
        by_priority[d.metadata["priority"]] += 1
    print(f"[doc_loader] By priority: {by_priority}")

    return docs


if __name__ == "__main__":
    load_all_documents()
