"""
config.py

Single source of truth for paths and settings used across the RAG
pipeline modules (doc_loader, text_splitter, vector_store, retriever,
build_index). Change a setting here once instead of hunting through
multiple files.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Input paths -- where webscrap_multi.py and pdf_pipeline.py wrote their output
# ---------------------------------------------------------------------------

SITEMAP_DIR = Path("scraped_pages/via_sitemap")
BFS_DIR = Path("scraped_pages/via_bfs")
PDF_TEXT_DIR = Path("pdfs_text")

# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

CHUNK_SIZE = 1000       # characters per chunk
CHUNK_OVERLAP = 150     # characters of overlap between consecutive chunks

# ---------------------------------------------------------------------------
# Embeddings -- via LangChain's HuggingFaceEmbeddings wrapper (local, free,
# no API key). Using LangChain here (instead of calling sentence-transformers
# directly) means swapping providers later -- e.g. to a hosted API, Gemini,
# OpenAI -- is a matter of swapping the Embeddings object in vector_store.py,
# not restructuring the pipeline.
#
# Model: jina-embeddings-v2-small-en was tried first (per your prior
# LangChain project) but FAILED on this machine -- its trust_remote_code
# custom modeling file imports `transformers.onnx`, a module HuggingFace
# removed from recent `transformers` versions (that ONNX-export tooling
# moved to the separate `optimum` package). Jina's 2023-era custom code
# just doesn't load against a current transformers install.
#
# Switched to BAAI/bge-small-en-v1.5: standard BERT-family architecture,
# no custom remote code to break, actively maintained, strong retrieval
# quality (consistently ranks well on the MTEB retrieval leaderboard),
# similar size/speed to Jina-small. If you want to revisit Jina later,
# it would need transformers pinned to an older compatible version --
# risky since crawl4ai/playwright also depend on transformers indirectly.
# ---------------------------------------------------------------------------

EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_MODEL_KWARGS = {}  # no trust_remote_code needed -- standard architecture
EMBEDDING_ENCODE_KWARGS = {
    "normalize_embeddings": True,
    "batch_size": 128,  # larger batch = fewer Python round-trips, less progress-bar spam, better CPU throughput
}

CHROMA_DB_DIR = Path("chroma_db")
COLLECTION_NAME = "vit_knowledge_base"

# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

DEFAULT_N_RESULTS = 3