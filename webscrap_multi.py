"""
webscrap_multi.py

Runs TWO discovery strategies and compares them:

1. SITEMAP - pulls URLs from VIT sitemap.xml, prioritizes relevant pages,
   and crawls them one at a time to reduce memory usage.

2. BFS LINK - starts at the homepage and follows internal links outward.

Both use Crawl4AI's PruningContentFilter to remove navigation/footer
boilerplate before markdown generation.

Tested against Crawl4AI 0.9.2.

Run:
    & "C:\\Users\\Aditya Gupta\\AppData\\Local\\Programs\\Python\\Python313\\python.exe" -u "webscrap_multi.py"
"""

import asyncio
import re
from pathlib import Path
from xml.etree import ElementTree

import requests

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
    BFSDeepCrawlStrategy,
    PruningContentFilter,
    DefaultMarkdownGenerator,
    FilterChain,
    DomainFilter,
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = "https://www.vit.edu/"
SITEMAP_URL = "https://www.vit.edu/sitemap.xml"

# Production run: crawl all keyword-relevant pages, plus a small buffer of
# other sitemap pages in case anything useful wasn't caught by keywords.
MAX_RELEVANT_PAGES = 60   # your test found 48 relevant URLs -- this covers them
MAX_OTHER_PAGES = 10      # small fallback budget for non-keyword-matched pages
MAX_PAGES = MAX_RELEVANT_PAGES + MAX_OTHER_PAGES  # kept for BFS, which has no relevant/other split

# BFS explores the link graph rather than targeting keywords, so it tends to
# wander into policy/compliance pages (AQAR, NIRF, etc). Useful as a
# complementary pass, but don't let it dominate the crawl budget.
BFS_MAX_PAGES = 30

RELEVANT_KEYWORDS = [
    "admission",
    "course",
    "programme",
    "program",
    "fee",
    "eligibil",
    "undergraduate",
    "postgraduate",
    "about",
    "placement",
    "department",
]

OUTPUT_DIR = Path("scraped_pages")
SITEMAP_DIR = OUTPUT_DIR / "via_sitemap"
BFS_DIR = OUTPUT_DIR / "via_bfs"


def normalize_url(url: str) -> str:
    """Collapse case/trailing-slash variants so /Undergraduate/ and
    /undergraduate/ are recognized as the same page. Used by BOTH
    strategies now -- the sitemap side had no dedup before, which is
    why page_01/page_07 and page_03/page_08 came back identical."""
    return url.strip().rstrip("/").lower()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


# ---------------------------------------------------------------------------
# Content filtering
# ---------------------------------------------------------------------------

def get_content_filter_config():
    """
    Creates the markdown generator using Crawl4AI's
    PruningContentFilter to remove boilerplate.
    """

    md_generator = DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(
            threshold=0.48,
            threshold_type="fixed",
            min_word_threshold=10,
        )
    )

    return md_generator


# ---------------------------------------------------------------------------
# Sitemap discovery
# ---------------------------------------------------------------------------

def fetch_sitemap_urls():
    """
    Fetch sitemap.xml and return relevant URLs first.
    """

    print("[sitemap] Fetching sitemap...")

    resp = requests.get(
        SITEMAP_URL,
        headers=HEADERS,
        timeout=15,
    )

    resp.raise_for_status()

    root = ElementTree.fromstring(resp.content)

    # Sitemap XML namespace handling
    ns = (
        {"sm": root.tag.split("}")[0].strip("{")}
        if "}" in root.tag
        else {}
    )

    loc_tag = (
        f"{{{ns['sm']}}}loc"
        if ns
        else "loc"
    )

    all_urls = [
        el.text.strip()
        for el in root.iter(loc_tag)
        if el.text
    ]

    # Remove PDF URLs before browser crawling.
    html_urls = [
        u for u in all_urls
        if not re.search(r"\.pdf(?:$|\?)", u, re.IGNORECASE)
    ]

    # Dedup case/trailing-slash variants (e.g. /Undergraduate/ vs
    # /undergraduate/), keeping the first-seen form of each.
    seen_normalized = set()
    deduped_urls = []
    for u in html_urls:
        norm = normalize_url(u)
        if norm in seen_normalized:
            continue
        seen_normalized.add(norm)
        deduped_urls.append(u)

    dupes_removed = len(html_urls) - len(deduped_urls)
    if dupes_removed:
        print(f"[sitemap] Removed {dupes_removed} case/slash-duplicate URLs")

    html_urls = deduped_urls

    relevant = [
        u
        for u in html_urls
        if any(k in u.lower() for k in RELEVANT_KEYWORDS)
    ]

    others = [
        u
        for u in html_urls
        if u not in relevant
    ]

    print(
        f"[sitemap] {len(all_urls)} total URLs found, "
        f"{len(relevant)} matched relevance keywords"
    )

    if len(all_urls) != len(html_urls):
        print(
            f"[sitemap] Skipped "
            f"{len(all_urls) - len(html_urls)} PDF URLs"
        )

    return relevant, others


# ---------------------------------------------------------------------------
# Strategy 1: Sitemap-based crawling
# ---------------------------------------------------------------------------

async def crawl_via_sitemap():

    relevant_urls, other_urls = fetch_sitemap_urls()
    urls = relevant_urls[:MAX_RELEVANT_PAGES] + other_urls[:MAX_OTHER_PAGES]
    print(
        f"[sitemap] Using {len(relevant_urls[:MAX_RELEVANT_PAGES])} relevant "
        f"+ {len(other_urls[:MAX_OTHER_PAGES])} fallback pages "
        f"= {len(urls)} total"
    )

    if not urls:
        print(
            "[sitemap] No URLs found -- "
            "check sitemap.xml is reachable and has entries."
        )
        return []

    SITEMAP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    run_config = CrawlerRunConfig(
        markdown_generator=get_content_filter_config(),
        cache_mode=CacheMode.BYPASS,
    )

    browser_config = BrowserConfig(
        headers=HEADERS
    )

    results_summary = []

    print()
    print(
        f"[sitemap] Testing {len(urls)} pages "
        f"one at a time..."
    )
    print()

    async with AsyncWebCrawler(
        config=browser_config
    ) as crawler:

        for i, url in enumerate(urls):

            print(
                f"[sitemap] Crawling "
                f"{i + 1}/{len(urls)}: {url}"
            )

            try:

                result = await crawler.arun(
                    url,
                    config=run_config,
                )

            except Exception as e:

                print(
                    f"[sitemap] ERROR: "
                    f"{url} -> {e}"
                )

                continue

            if not result.success:

                print(
                    f"[sitemap] FAILED: "
                    f"{result.url} -> "
                    f"{result.error_message}"
                )

                continue

            if hasattr(
                result.markdown,
                "fit_markdown",
            ):

                md = result.markdown.fit_markdown

            else:

                md = str(result.markdown)

            fname = (
                SITEMAP_DIR
                / f"page_{i:02d}.md"
            )

            fname.write_text(
                md,
                encoding="utf-8",
            )

            results_summary.append(
                (
                    result.url,
                    len(md),
                )
            )

            print(
                f"[sitemap] saved "
                f"{fname.name} "
                f"({len(md)} chars) "
                f"<- {result.url}"
            )

            print()

    return results_summary


# ---------------------------------------------------------------------------
# Strategy 2: BFS link-following
# ---------------------------------------------------------------------------

async def crawl_via_bfs():

    BFS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    filter_chain = FilterChain(
        [
            DomainFilter(
                allowed_domains=[
                    "vit.edu",
                    "www.vit.edu",
                ]
            ),
        ]
    )

    deep_crawl_strategy = BFSDeepCrawlStrategy(
        max_depth=2,
        max_pages=BFS_MAX_PAGES,
        filter_chain=filter_chain,
        include_external=False,
    )

    run_config = CrawlerRunConfig(
        markdown_generator=get_content_filter_config(),
        deep_crawl_strategy=deep_crawl_strategy,
        cache_mode=CacheMode.BYPASS,
        stream=False,
    )

    browser_config = BrowserConfig(
        headers=HEADERS
    )

    results_summary = []

    print(
        f"[bfs] Starting BFS crawl "
        f"(max {BFS_MAX_PAGES} pages)..."
    )

    async with AsyncWebCrawler(
        config=browser_config
    ) as crawler:

        try:

            results = await crawler.arun(
                BASE_URL,
                config=run_config,
            )

        except Exception as e:

            print(
                f"[bfs] ERROR: {e}"
            )

            return results_summary

        if not isinstance(results, list):
            results = [results]

        seen_urls = set()

        for i, result in enumerate(results):

            if not result.success:

                print(
                    f"[bfs] FAILED: "
                    f"{result.url} -> "
                    f"{result.error_message}"
                )

                continue

            # Extra URL deduplication (shared logic with the sitemap side)
            normalized_url = normalize_url(result.url)

            if normalized_url in seen_urls:
                print(
                    f"[bfs] SKIPPED duplicate: "
                    f"{result.url}"
                )
                continue

            seen_urls.add(normalized_url)

            if hasattr(
                result.markdown,
                "fit_markdown",
            ):

                md = result.markdown.fit_markdown

            else:

                md = str(result.markdown)

            safe_name = re.sub(
                r"[^a-zA-Z0-9]+",
                "_",
                result.url,
            )[:60]

            fname = (
                BFS_DIR
                / f"page_{i:02d}_{safe_name}.md"
            )

            fname.write_text(
                md,
                encoding="utf-8",
            )

            results_summary.append(
                (
                    result.url,
                    len(md),
                )
            )

            print(
                f"[bfs] saved "
                f"{fname.name} "
                f"({len(md)} chars) "
                f"<- {result.url}"
            )

    return results_summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():

    print("=" * 70)
    print("STRATEGY 1: Sitemap-based discovery")
    print("=" * 70)

    sitemap_results = await crawl_via_sitemap()

    print()
    print("=" * 70)
    print("STRATEGY 2: BFS link-following discovery")
    print("=" * 70)

    bfs_results = await crawl_via_bfs()

    print()
    print("=" * 70)
    print("COMPARISON")
    print("=" * 70)

    print(
        f"Sitemap strategy: "
        f"{len(sitemap_results)} pages "
        f"saved to {SITEMAP_DIR}/"
    )

    print(
        f"BFS strategy:     "
        f"{len(bfs_results)} pages "
        f"saved to {BFS_DIR}/"
    )

    if sitemap_results:

        avg = (
            sum(
                length
                for _, length in sitemap_results
            )
            / len(sitemap_results)
        )

        print(
            f"Sitemap avg content length: "
            f"{avg:.0f} chars/page"
        )

    if bfs_results:

        avg = (
            sum(
                length
                for _, length in bfs_results
            )
            / len(bfs_results)
        )

        print(
            f"BFS avg content length: "
            f"{avg:.0f} chars/page"
        )

    print()
    print(
        "Open a couple of the saved .md files "
        "in each folder and check:"
    )

    print(
        "  - Is real content present "
        "(courses/fees/eligibility)?"
    )

    print(
        "  - Is nav/footer boilerplate gone?"
    )

    print(
        "  - Which strategy reached "
        "the more useful pages?"
    )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(main())