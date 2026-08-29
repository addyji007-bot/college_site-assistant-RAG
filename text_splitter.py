"""
text_splitter.py

Chunks LangChain Documents using RecursiveCharacterTextSplitter (tries
paragraph breaks first, then sentences, then words -- falls back
gracefully instead of cutting mid-word like a naive fixed-size split).

Run this file directly to sanity-check chunking on a sample Document:
    python text_splitter.py
"""

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

import config


def get_splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
    )


def chunk_documents(docs: list[Document]) -> list[Document]:
    """Chunk each doc individually (rather than one big split_documents()
    call) so we can assign clean, traceable ids per source doc."""
    splitter = get_splitter()
    all_chunks = []
    for doc_idx, doc in enumerate(docs):
        chunks = splitter.split_documents([doc])
        for chunk_idx, chunk in enumerate(chunks):
            chunk.metadata["chunk_id"] = f"doc{doc_idx}_chunk{chunk_idx}"
            all_chunks.append(chunk)

    print(f"[text_splitter] {len(all_chunks)} chunks from {len(docs)} documents")
    return all_chunks


if __name__ == "__main__":
    sample = Document(
        page_content="\n\n".join(f"Paragraph {i}. " + ("Sample text. " * 10) for i in range(15)),
        metadata={"source_url": "test"},
    )
    chunks = chunk_documents([sample])
    print(f"Sample input: {len(sample.page_content)} chars -> {len(chunks)} chunks")
    for c in chunks:
        print(f"  {c.metadata['chunk_id']}: {len(c.page_content)} chars")
