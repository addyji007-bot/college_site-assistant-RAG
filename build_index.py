"""
build_index.py

Orchestrates the RAG indexing pipeline (now LangChain-based throughout):
  doc_loader    -> load HTML + PDF docs as LangChain Documents, dedup
  text_splitter -> chunk with RecursiveCharacterTextSplitter
  vector_store  -> embed (HuggingFaceEmbeddings) + store in Chroma
  retriever     -> validate with test queries

Run this whenever you've re-scraped (webscrap_multi.py / pdf_pipeline.py)
and want to rebuild the searchable index:
    python -u build_index.py
"""

import doc_loader
import text_splitter
import vector_store
import retriever


def main():
    print("=" * 70)
    print("STEP 1: Loading documents")
    print("=" * 70)
    docs = doc_loader.load_all_documents()

    if not docs:
        print("[build_index] No documents found. Run webscrap_multi.py and pdf_pipeline.py first.")
        return

    print()
    print("=" * 70)
    print("STEP 2: Chunking")
    print("=" * 70)
    chunks = text_splitter.chunk_documents(docs)

    print()
    print("=" * 70)
    print("STEP 3: Embedding + storing")
    print("=" * 70)
    vector_store.build_vectorstore(chunks)

    print()
    print("=" * 70)
    print("STEP 4: Validation queries")
    print("=" * 70)
    test_questions = [
        "What is the fee for BTech Computer Engineering?",
        "What is the eligibility criteria for admission?",
        "What placement support does VIT offer?",
    ]
    for q in test_questions:
        results = retriever.retrieve(q)
        retriever.print_results(q, results)

    print()
    print("Index built. Query it later with: python retriever.py")


if __name__ == "__main__":
    main()
