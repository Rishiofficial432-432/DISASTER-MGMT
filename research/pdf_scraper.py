"""
PDF scraper for government guideline pages (NDMA, MoHUA, etc.)

- Adds a delay between requests (avoid rate-limiting / blocks)
- Retries transient failures with backoff
- Verifies Content-Type is actually a PDF before saving (avoids saving
  HTML error pages with a .pdf extension)
- Disambiguates filenames by prefixing a short hash of the URL, so two
  PDFs with the same basename from different pages don't overwrite each other
- Skips re-downloading a file that's already on disk
- Respects robots.txt (best-effort; skips a page if disallowed)

Usage: python pdf_scraper.py
Output: pdfs/ directory + scraped_pdfs_manifest.csv
"""

import os
import re
import csv
import time
import hashlib
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

PAGES = [
    "https://ndma.gov.in/Governance/Guidelines",
    "https://mohua.gov.in/link/urdpfi-guidelines.php",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PDFScraper/1.1; +research use)"
}

REQUEST_DELAY_SEC = 2       # politeness delay between requests
MAX_RETRIES = 3
RETRY_BACKOFF_SEC = 5
TIMEOUT = 30
DOWNLOAD_TIMEOUT = 60


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())[:180].strip("_") or "file"


def url_hash(url: str) -> str:
    """Short stable hash to disambiguate same-named files from different pages/URLs."""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]


def robots_allows(url: str) -> bool:
    """Best-effort robots.txt check. If robots.txt can't be fetched, default to allow."""
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(HEADERS["User-Agent"], url)
    except Exception:
        return True  # fail open if robots.txt is unreachable


def request_with_retries(url: str, stream: bool = False):
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT if not stream else DOWNLOAD_TIMEOUT, stream=stream)
            r.raise_for_status()
            return r
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SEC * attempt)
    raise last_err


def get_links(page_url: str):
    if not robots_allows(page_url):
        raise PermissionError(f"robots.txt disallows fetching {page_url}")

    r = request_with_retries(page_url)
    soup = BeautifulSoup(r.text, "html.parser")

    items = []
    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, a["href"])
        text = " ".join(a.get_text(" ", strip=True).split())
        if ".pdf" in href.lower() or "download" in text.lower():
            items.append((text or os.path.basename(urlparse(href).path), href))

    seen = set()
    uniq = []
    for t, h in items:
        if h not in seen:
            seen.add(h)
            uniq.append((t, h))
    return uniq


def download(url: str, folder: str = "pdfs") -> str:
    os.makedirs(folder, exist_ok=True)

    base_fn = os.path.basename(urlparse(url).path) or "download.pdf"
    if not base_fn.lower().endswith(".pdf"):
        base_fn += ".pdf"

    fn = f"{url_hash(url)}_{safe_name(base_fn)}"
    path = os.path.join(folder, fn)

    if os.path.exists(path):
        return path  # already downloaded, skip re-fetching

    r = request_with_retries(url, stream=True)

    content_type = r.headers.get("Content-Type", "").lower()
    if "pdf" not in content_type and not url.lower().endswith(".pdf"):
        raise ValueError(f"URL did not return a PDF (Content-Type: {content_type or 'unknown'})")

    with open(path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)

    return path


def main():
    rows = []
    for page in PAGES:
        print(f"Scanning: {page}")
        try:
            links = get_links(page)
            print(f"  found {len(links)} candidate PDF link(s)")
            for title, pdf_url in links:
                time.sleep(REQUEST_DELAY_SEC)
                try:
                    local = download(pdf_url)
                    status = "ok"
                    print(f"  [ok] {title[:60]!r} -> {local}")
                except Exception as e:
                    local = ""
                    status = f"download_error:{e}"
                    print(f"  [fail] {title[:60]!r}: {e}")
                rows.append({
                    "page": page,
                    "title": title,
                    "pdf_url": pdf_url,
                    "local_path": local,
                    "status": status,
                })
        except Exception as e:
            print(f"  [page error] {e}")
            rows.append({
                "page": page,
                "title": "",
                "pdf_url": "",
                "local_path": "",
                "status": f"page_error:{e}",
            })
        time.sleep(REQUEST_DELAY_SEC)

    with open("scraped_pdfs_manifest.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["page", "title", "pdf_url", "local_path", "status"])
        writer.writeheader()
        writer.writerows(rows)

    ok_count = sum(1 for r in rows if r["status"] == "ok")
    print(f"\nDone. {ok_count}/{len(rows)} downloaded successfully.")
    print("Manifest: scraped_pdfs_manifest.csv")


if __name__ == "__main__":
    main()
