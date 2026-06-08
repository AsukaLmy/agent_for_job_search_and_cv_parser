"""
Diagnostic: fetch each scraper's first search page and report
  - HTTP status / response length
  - whether the expected CSS selectors are found
  - first 1000 chars of raw HTML (to spot JS-shell or Cloudflare blocks)

Run:  python debug_scrapers.py
No DB writes, no AI calls.
"""
import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def check(name: str, url: str, selectors: list[str]) -> None:
    print(f"\n{'='*65}")
    print(f"[{name}]  {url}")
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
        print(f"  Status : {resp.status_code}")
        print(f"  Length : {len(resp.text):,} chars")
        soup = BeautifulSoup(resp.text, "lxml")
        for sel in selectors:
            n = len(soup.select(sel))
            mark = "✓" if n > 0 else "✗"
            print(f"  {mark} '{sel}' → {n} hits")
        print(f"\n  -- HTML snippet (first 1000 chars) --")
        print(resp.text[:1000])
    except Exception as exc:
        print(f"  ERROR: {exc}")


# ── 智联招聘 ──────────────────────────────────────────────
check(
    "智联招聘",
    "https://sou.zhaopin.com/?jl=%E5%85%A8%E5%9B%BD&kw=%E7%AE%97%E6%B3%95%E5%B7%A5%E7%A8%8B%E5%B8%88&p=1",
    [
        "div.joblist-box__item",
        "li.job-item",
        "div[class*='job']",
        "li[class*='job']",
        "a[class*='job']",
    ],
)

# ── FindAPhD ──────────────────────────────────────────────
check(
    "FindAPhD",
    "https://www.findaphd.com/phds/?Keywords=machine+learning&PhdFullTime=1&PageNumber=1",
    [
        "div.phd-result",
        "div[class*='phd-result']",
        "div[class*='result']",
        "article",
        "div[class*='ResultItem']",
    ],
)

# ── PhDPortals ────────────────────────────────────────────
check(
    "PhDPortals",
    "https://www.phdportal.eu/search/?q=machine+learning&degree=phd&page=1",
    [
        "article.course-card",
        "div.programme-card",
        "article",
        "div[class*='card']",
        "div[class*='programme']",
        "li[class*='programme']",
    ],
)
