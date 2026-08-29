"""
vector_store.py

Embedding generation and Chroma storage, via LangChain.

DESIGN NOTE -- built for "works locally today, official tomorrow":
get_embedding_function() is the single swap point. Today it wraps a
local Jina model through LangChain's HuggingFaceEmbeddings (free, no API
key, no rate limits). Moving to a hosted embedding provider later (Jina's
API, Gemini, OpenAI) means swapping the Embeddings object returned here
for a different LangChain integration -- e.g. langchain_google_genai's
GoogleGenerativeAIEmbeddings -- nothing in doc_loader.py, text_splitter.py,
or retriever.py needs to change, since they only depend on the
LangChain Embeddings/VectorStore interfaces, not this specific provider.

On speed: embedding ~9000 chunks on a CPU genuinely takes a few minutes --
that's inference cost, not a bug. What WAS wasteful before was calling
.encode() in small 64-chunk batches with a progress bar printed per call.
Passing the whole chunk list to Chroma.from_documents() in one call lets
LangChain/sentence-transformers batch internally (EMBEDDING_ENCODE_KWARGS
controls that internal batch size) -- fewer Python round-trips, one
clean progress bar instead of 140+ of them.

Run this file directly to check the embedding function loads correctly:
    python vector_store.py
"""

from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

import config

_embeddings_cache = None  # avoid reloading the model on every call within one process


def get_embedding_function() -> HuggingFaceEmbeddings:
    """Returns a LangChain Embeddings object. Cached per process so
    retriever.py doesn't reload the model on every query."""
    global _embeddings_cache
    if _embeddings_cache is not None:
        return _embeddings_cache

    print(f"[vector_store] Loading embedding model '{config.EMBEDDING_MODEL_NAME}' "
          f"(first run downloads it)...")
    _embeddings_cache = HuggingFaceEmbeddings(
        model_name=config.EMBEDDING_MODEL_NAME,
        model_kwargs=config.EMBEDDING_MODEL_KWARGS,
        encode_kwargs=config.EMBEDDING_ENCODE_KWARGS,
    )
    return _embeddings_cache


def get_existing_vectorstore() -> Chroma:
    """For querying an already-built index (used by retriever.py) --
    does NOT rebuild anything."""
    return Chroma(
        collection_name=config.COLLECTION_NAME,
        embedding_function=get_embedding_function(),
        persist_directory=str(config.CHROMA_DB_DIR),
    )


def build_vectorstore(chunks: list[Document]) -> Chroma:
    """Fresh build each run -- simplest correct behavior while iterating.
    Once this is stable, switch to incremental upserts instead of a full
    rebuild (e.g. only re-embed chunks whose source doc changed)."""
    embeddings = get_embedding_function()
    ids = [c.metadata["chunk_id"] for c in chunks]

    print(f"[vector_store] Embedding + storing {len(chunks)} chunks "
          f"(this is the slow step -- CPU inference over every chunk, expect a few minutes)...")
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        ids=ids,
        collection_name=config.COLLECTION_NAME,
        persist_directory=str(config.CHROMA_DB_DIR),
    )
    print(f"[vector_store] Done. Collection '{config.COLLECTION_NAME}' saved to {config.CHROMA_DB_DIR}/")
    return vectorstore


if __name__ == "__main__":
    embeddings = get_embedding_function()
    vec = embeddings.embed_query("sanity check")
    print(f"Embedding function OK -- vector length {len(vec)}")
