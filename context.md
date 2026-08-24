# Crawl4AI Project Context

## Project

We are building a Python web-scraping project using **Crawl4AI** to scrape the VIT website.

**Project location:**

```text
C:\Users\Aditya Gupta\OneDrive\Desktop\demo\
```

**Target website:**

https://www.vit.edu/

**Main Python file:**

```text
webscrap.py
```

**Python installation:**

```text
C:\Users\Aditya Gupta\AppData\Local\Programs\Python\Python313\python.exe
```

**Python version:**

```text
Python 3.13
```

---

## What We Started With

The original code was:

```python
import asyncio

from crawl4ai import AsyncWebCrawler

async def main():

    async with AsyncWebCrawler() as crawler:

        result = await crawler.arun("https://www.vit.edu/")

        print(result.markdown[:300])

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Problem 1: Crawl4AI Was Not Installed

Initially, running the script produced:

```text
ModuleNotFoundError: No module named 'crawl4ai'
```

The fix was to install Crawl4AI into the Python 3.13 environment:

```powershell
& "C:\Users\Aditya Gupta\AppData\Local\Programs\Python\Python313\python.exe" -m pip install crawl4ai
```

After installation, the import worked:

```python
from crawl4ai import AsyncWebCrawler
```

---

## Problem 2: Playwright Browser Was Missing

After installing Crawl4AI, the script failed with:

```text
BrowserType.launch: Executable doesn't exist at

C:\Users\Aditya Gupta\AppData\Local\ms-playwright\chromium\_headless\_shell-1234\chrome-headless-shell-win64\chrome-headless-shell.exe
```

This meant that Playwright was installed, but its Chromium browser binaries were not installed.

The fix was:

```powershell
& "C:\Users\Aditya Gupta\AppData\Local\Programs\Python\Python313\python.exe" -m playwright install chromium
```

This successfully downloaded:

* Chrome for Testing / Chromium
* Chromium Headless Shell
* FFmpeg
* Winldd

The browser files were installed under:

```text
C:\Users\Aditya Gupta\AppData\Local\ms-playwright\
```

---

## Successful Run

After installing Chromium, the scraper successfully ran.

Output:

```text
[INIT].... → Crawl4AI 0.9.2

[FETCH]... ↓ https://www.vit.edu/ | ✓ | ⏱: 2.59s

[SCRAPE].. ◆ https://www.vit.edu/ | ✓ | ⏱: 0.08s

[COMPLETE] ● https://www.vit.edu/ | ✓ | ⏱: 2.70s
```

It successfully extracted Markdown from VIT.

Example output:

```markdown
[About](https://www.vit.edu/)

* [Institute](https://www.vit.edu/about/)
* [Core Values](https://www.vit.edu/core-values/)
* [Infrastructure](https://www.vit.edu/infrastructure)
* [Approvals](https://www.vit.edu/aicte-approval)
* [Sustainability Development](https://www.vit.edu/sustainabi)
```

The program finished with:

```text
[Done] exited with code 0
```

Exit code `0` means the program completed successfully.

---

## Current Working Code

The current working code is:

```python
import asyncio

from crawl4ai import AsyncWebCrawler

async def main():

    async with AsyncWebCrawler() as crawler:

        result = await crawler.arun("https://www.vit.edu/")

        print(result.markdown[:300])

if __name__ == "__main__":
    asyncio.run(main())
```

This code is currently working.

---

## Important Warning

The program also shows:

```text
RequestsDependencyWarning:
```

The warning indicates that the installed versions of `urllib3`, `chardet`, or `charset_normalizer` do not exactly match the versions expected by the installed `requests` package.

This is currently **only a warning**.

It does **not** prevent Crawl4AI from working because the scraper successfully completed.

If we want to clean it up later, we can run:

```powershell
& "C:\Users\Aditya Gupta\AppData\Local\Programs\Python\Python313\python.exe" -m pip install --upgrade requests urllib3 charset-normalizer
```

For now, this warning can be ignored because the scraper is functioning correctly.

---

## Current Architecture

```text
Python 3.13
    ↓
Crawl4AI 0.9.2
    ↓
Playwright
    ↓
Chromium
    ↓
VIT Website
https://www.vit.edu/
    ↓
Scraped HTML
    ↓
Markdown
    ↓
result.markdown
```

---

## Better Version for Saving Scraped Data

Currently, the script only prints the first 300 characters:

```python
print(result.markdown[:300])
```

A better version is to save the entire scraped page into a Markdown file:

```python
import asyncio

from crawl4ai import AsyncWebCrawler

async def main():

    async with AsyncWebCrawler() as crawler:

        result = await crawler.arun("https://www.vit.edu/")

        with open("vit_website.md", "w", encoding="utf-8") as f:
            f.write(result.markdown)

        print("Scraping complete!")
        print(f"Characters extracted: {len(result.markdown)}")

if __name__ == "__main__":
    asyncio.run(main())
```

This would create:

```text
demo/
├── webscrap.py
├── vit_website.md
└── context.md
```

`vit_website.md` will contain the complete Markdown extracted from the VIT homepage.

---

## Useful Commands

### Check Python version

```powershell
python.exe --version
```

### Check which Python is being used

```powershell
python.exe -c "import sys; print(sys.executable)"
```

Expected Python executable:

```text
C:\Users\Aditya Gupta\AppData\Local\Programs\Python\Python313\python.exe
```

### Check Crawl4AI version

```powershell
python.exe -c "import crawl4ai; print(crawl4ai.__version__)"
```

Current Crawl4AI version observed:

```text
0.9.2
```

### Check Playwright

```powershell
python.exe -m playwright --help
```

### Install Chromium for Playwright

```powershell
python.exe -m playwright install chromium
```

### Run the scraper

```powershell
python.exe -u "C:\Users\Aditya Gupta\OneDrive\Desktop\demo\webscrap.py"
```

---

## Important Troubleshooting Note

If `crawl4ai` or Playwright appears to be installed but Python says it cannot find the package, make sure the package is being installed into the **same Python executable that runs the script**.

Use:

```powershell
& "C:\Users\Aditya Gupta\AppData\Local\Programs\Python\Python313\python.exe" -m pip install crawl4ai
```

instead of relying on a random/global `pip`.

Similarly, for Playwright:

```powershell
& "C:\Users\Aditya Gupta\AppData\Local\Programs\Python\Python313\python.exe" -m playwright install chromium
```

This ensures that the packages and browser dependencies are installed for the correct Python environment.

---

# Current Status

## Completed

* [x] Python 3.13 setup
* [x] Crawl4AI installation
* [x] Playwright installation
* [x] Chromium installation
* [x] Crawl4AI browser initialization
* [x] VIT website fetching
* [x] VIT website scraping
* [x] Markdown extraction
* [x] Successful execution with exit code `0`

## Not Yet Done

* [ ] Crawl all pages of VIT instead of only the homepage
* [ ] Automatically discover internal links
* [ ] Store all scraped pages
* [ ] Clean and normalize scraped content
* [ ] Remove duplicate content
* [ ] Split content into chunks
* [ ] Generate embeddings
* [ ] Store embeddings in a vector database
* [ ] Build a RAG system
* [ ] Build a VIT-focused chatbot

---

# Future Goal

The long-term goal is to turn the VIT website into a searchable knowledge base that can answer user questions using information retrieved directly from the official VIT website.

Potential pipeline:

```text
VIT Website
    ↓
Crawl4AI
    ↓
Discover Internal Pages
    ↓
Scrape All Relevant Pages
    ↓
Clean Markdown
    ↓
Remove Duplicates
    ↓
Chunk Documents
    ↓
Generate Embeddings
    ↓
Vector Database
    ↓
Retriever
    ↓
LLM
    ↓
VIT Chatbot
```

---

# Immediate Next Step

The immediate next step is to modify the current scraper so that it can **crawl multiple pages of `vit.edu` automatically**, rather than only scraping:

```text
https://www.vit.edu/
```

The basic Crawl4AI + Playwright setup is already working.

There is currently **no browser installation issue that needs to be fixed**.

The next development focus should therefore be:

```text
Homepage
    ↓
Find internal VIT links
    ↓
Visit those links
    ↓
Extract content
    ↓
Continue discovering relevant internal links
    ↓
Store all scraped content
```

After the multi-page crawler is working reliably, the project can move toward the cleaning → chunking → embeddings → vector database → RAG → chatbot stages.
