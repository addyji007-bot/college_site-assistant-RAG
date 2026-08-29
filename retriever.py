"""
retriever.py

Queries an already-built Chroma collection via LangChain. Does NOT
rebuild the index -- run build_index.py first (or after any re-scrape)
to create/refresh it.

Run this file directly for an interactive test query loop:
    python retriever.py
"""

import config
import vector_store


def retrieve(question: str, n_results: int = None, where: dict = None) -> list[dict]:
    """Returns a list of {text, source_url, document_type, priority,
    academic_year, discovery_method} dicts, most relevant first.

    `where` is an optional Chroma metadata filter, e.g.:
        where={"priority": "HIGH"}
        where={"document_type": "fee_structure"}
    Useful once the knowledge base grows -- e.g. to only search HIGH
    priority docs, or restrict to a specific document type.
    """
    n_results = n_results or config.DEFAULT_N_RESULTS
    vectorstore = vector_store.get_existing_vectorstore()

    results = vectorstore.similarity_search(question, k=n_results, filter=where)

    return [{"text": doc.page_content, **doc.metadata} for doc in results]


def print_results(question: str, results: list[dict]):
    print(f"\n[retriever] Query: {question!r}")
    for i, r in enumerate(results):
        print(f"\n  Result {i + 1} [{r['document_type']} / {r['priority']} / {r['academic_year']}]")
        print(f"  Source: {r['source_url']}")
        print(f"  {r['text'][:300]}...")


if __name__ == "__main__":
    print("Interactive retrieval test. Type a question, or 'quit' to exit.")
    while True:
        q = input("\n> ").strip()
        if not q or q.lower() in ("quit", "exit"):
            break
        results = retrieve(q)
        print_results(q, results)
