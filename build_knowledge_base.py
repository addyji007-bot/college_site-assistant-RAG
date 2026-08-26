"""
build_knowledge_base.py

Phase C of the VIT Assist project: combine everything scraped so far
(HTML markdown + PDF text) into one chunked, embedded, queryable
knowledge base.

    scraped_pages/via_sitemap/*.md  +  metadata.json
    scraped_pages/via_bfs/*.md      +  metadata.json      -->  combine
    pdfs_text/*.txt                 +  metadata.json            |
                                                                  v
                                                              chunk
                                                                  |
                                                                  v
                                                        embed (pluggable)
                                                                  |
                                                                  v
                                                          Chroma (local)

DESIGN NOTE -- built for "works locally today, official tomorrow":
Embedding generation goes through get_embedding_function(), a single
swap point. Today it returns a local sentence-transformers model (free,
no API key, no rate limits, good for testing). If this later needs to
become a shared/official deployment, only that one function needs to
change -- e.g. to call Gemini's embedding API -- nothing about the
chunking, storage, or query logic below needs to be touched.

Run with your project's Python:
    & "C:\\Users\\Aditya Gupta\\AppData\\Local\\Programs\\Python\\Python313\\python.exe" -u "build_knowledge_base.py"

Requires: pip install sentence-transformers chromadb
"""

import json
import hashlib
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SITEMAP_DIR = Path("scraped_pages/via_sitemap")
BFS_DIR = Path("scraped_pages/via_bfs")
PDF_TEXT_DIR = Path("pdfs_text")

CHROMA_DB_DIR = Path("chroma_db")
COLLECTION_NAME = "vit_knowledge_base"

CHUNK_SIZE = 1000       # characters per chunk
CHUNK_OVERLAP = 150     # characters of overlap between consecutive chunks

# Embedding provider switch -- see get_embedding_function() below.
EMBEDDING_PROVIDER = "local"  # "local" today; "gemini" / "openai" later
LOCAL_EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # small, fast, good enough to validate the pipeline


# ---------------------------------------------------------------------------
# Step 1: Load + combine documents from both pipelines
# ---------------------------------------------------------------------------

def load_html_docs(folder: Path, source_label: str) -> list[dict]:
    """Load markdown pages + their metadata.json (url per file)."""
    meta_path = folder / "metadata.json"
    if not meta_path.exists():
        print(f"[combine] WARNING: no metadata.json in {folder} -- "
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
        docs.append({
            "text": text,
            "source_url": entry["source_url"],
            "source_type": "html",
            "document_type": "webpage",
            "priority": "HIGH",  # HTML pages were already keyword-filtered at crawl time
            "academic_year": None,
            "discovery_method": source_label,
        })
    print(f"[combine] Loaded {len(docs)} HTML docs from {folder}")
    return docs


def load_pdf_docs(folder: Path) -> list[dict]:
    """Load extracted PDF text + its metadata.json (from pdf_pipeline.py)."""
    meta_path = folder / "metadata.json"
    if not meta_path.exists():
        print(f"[combine] WARNING: no metadata.json in {folder} -- "
              f"run pdf_pipeline.py first. Skipping PDFs.")
        return []

    meta_list = json.loads(meta_path.read_text(encoding="utf-8"))
    docs = []
    for entry in meta_list:
        if not entry.get("local_text"):
            continue  # archived_only / needs_manual_review / failed -- no text to index
        fpath = Path(entry["local_text"])
        if not fpath.exists():
            continue
        text = fpath.read_text(encoding="utf-8")
        if not text.strip():
            continue
        docs.append({
            "text": text,
            "source_url": entry["source_url"],
            "source_type": "pdf",
            "document_type": entry["document_type"],
            "priority": entry["priority"],
            "academic_year": entry["academic_year"],
            "discovery_method": "pdf_pipeline",
        })
    print(f"[combine] Loaded {len(docs)} PDF docs from {folder}")
    return docs


def dedup_by_content(docs: list[dict]) -> list[dict]:
    """The sitemap and BFS strategies can both reach the same page (e.g.
    /about/). Dedup by content hash so it isn't indexed twice."""
    seen_hashes = set()
    deduped = []
    for doc in docs:
        h = hashlib.md5(doc["text"].encode("utf-8")).hexdigest()
        if h in seen_hashes:
            continue
        seen_hashes.add(h)
        deduped.append(doc)
    dropped = len(docs) - len(deduped)
    if dropped:
        print(f"[combine] Dropped {dropped} duplicate-content docs (same page reached twice)")
    return deduped


# ---------------------------------------------------------------------------
# Step 2: Chunking
# ---------------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Simple paragraph-aware chunker: split on blank lines first, then pack
    paragraphs into chunks up to chunk_size, carrying overlap between chunks
    so context isn't lost at boundaries. No extra dependency needed."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= chunk_size:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                chunks.append(current)
            # start new chunk, carrying a bit of overlap from the end of the last one
            overlap_text = current[-overlap:] if current else ""
            current = f"{overlap_text}\n\n{para}" if overlap_text else para
            # if a single paragraph is itself bigger than chunk_size, hard-split it
            while len(current) > chunk_size * 1.5:
                chunks.append(current[:chunk_size])
                current = current[chunk_size - overlap:]
    if current:
        chunks.append(current)

    return chunks


# ---------------------------------------------------------------------------
# Step 3: Embeddings (pluggable -- this is the single swap point)
# ---------------------------------------------------------------------------

def get_embedding_function():
    """Returns a function: list[str] -> list[list[float]].

    Swap point for the future: today this loads a local sentence-transformers
    model (free, offline, no rate limits -- right for validating the pipeline
    works). If/when this needs to become an official shared deployment,
    add an EMBEDDING_PROVIDER == "gemini" (or "openai") branch here that
    calls the hosted API instead -- nothing else in this file changes.
    """
    if EMBEDDING_PROVIDER == "local":
        print(f"[embed] Loading local model '{LOCAL_EMBEDDING_MODEL}' "
              f"(first run downloads it, ~90MB)...")
        model = SentenceTransformer(LOCAL_EMBEDDING_MODEL)

        def embed(texts: list[str]) -> list[list[float]]:
            return model.encode(texts, show_progress_bar=True, normalize_embeddings=True).tolist()

        return embed

    raise NotImplementedError(
        f"EMBEDDING_PROVIDER='{EMBEDDING_PROVIDER}' not implemented yet. "
        f"Add a branch here when moving to a hosted provider."
    )


# ---------------------------------------------------------------------------
# Step 4: Store in Chroma
# ---------------------------------------------------------------------------

def build_collection(docs: list[dict]):
    embed = get_embedding_function()

    client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
    # Fresh build each run -- simplest correct behavior while iterating.
    # Once this is stable, switch to incremental upserts instead of a full rebuild.
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(COLLECTION_NAME)

    all_chunks, all_metadatas, all_ids = [], [], []
    for doc_idx, doc in enumerate(docs):
        chunks = chunk_text(doc["text"])
        for chunk_idx, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            all_metadatas.append({
                "source_url": doc["source_url"],
                "source_type": doc["source_type"],
                "document_type": doc["document_type"],
                "priority": doc["priority"],
                "academic_year": doc["academic_year"] or "unknown",
                "discovery_method": doc["discovery_method"],
            })
            all_ids.append(f"doc{doc_idx}_chunk{chunk_idx}")

    print(f"[embed] {len(all_chunks)} chunks from {len(docs)} documents. Embedding...")

    # Batch to keep memory bounded -- same lesson as the crawler's memory issue.
    batch_size = 64
    for start in range(0, len(all_chunks), batch_size):
        end = start + batch_size
        batch_texts = all_chunks[start:end]
        batch_embeddings = embed(batch_texts)
        collection.add(
            documents=batch_texts,
            embeddings=batch_embeddings,
            metadatas=all_metadatas[start:end],
            ids=all_ids[start:end],
        )
        print(f"[embed]   stored {min(end, len(all_chunks))}/{len(all_chunks)} chunks")

    print(f"[embed] Done. Collection '{COLLECTION_NAME}' saved to {CHROMA_DB_DIR}/")
    return collection


# ---------------------------------------------------------------------------
# Step 5: Quick validation query
# ---------------------------------------------------------------------------

def test_query(collection, question: str, n_results: int = 3):
    embed = get_embedding_function()
    query_embedding = embed([question])[0]
    results = collection.query(query_embeddings=[query_embedding], n_results=n_results)

    print(f"\n[test] Query: {question!r}")
    for i, (doc, meta) in enumerate(zip(results["documents"][0], results["metadatas"][0])):
        print(f"\n  Result {i + 1} [{meta['document_type']} / {meta['priority']} / {meta['academic_year']}]")
        print(f"  Source: {meta['source_url']}")
        print(f"  {doc[:300]}...")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("STEP 1: Loading and combining documents")
    print("=" * 70)

    docs = []
    docs += load_html_docs(SITEMAP_DIR, "sitemap")
    docs += load_html_docs(BFS_DIR, "bfs")
    docs += load_pdf_docs(PDF_TEXT_DIR)
    docs = dedup_by_content(docs)

    print(f"\n[combine] Total documents to index: {len(docs)}")
    by_priority = {}
    for d in docs:
        by_priority.setdefault(d["priority"], 0)
        by_priority[d["priority"]] += 1
    print(f"[combine] By priority: {by_priority}")

    if not docs:
        print("[combine] No documents found. Run webscrap_multi.py and pdf_pipeline.py first.")
        return

    print()
    print("=" * 70)
    print("STEP 2-4: Chunking, embedding, and storing")
    print("=" * 70)
    collection = build_collection(docs)

    print()
    print("=" * 70)
    print("STEP 5: Validation queries")
    print("=" * 70)
    test_questions = [
        "What is the fee for BTech Computer Engineering?",
        "What is the eligibility criteria for admission?",
        "What placement support does VIT offer?",
    ]
    for q in test_questions:
        test_query(collection, q)

    print()
    print("Knowledge base built. To query it later without re-embedding everything:")
    print("  client = chromadb.PersistentClient(path='chroma_db')")
    print(f"  collection = client.get_collection('{COLLECTION_NAME}')")


if __name__ == "__main__":
    main()
