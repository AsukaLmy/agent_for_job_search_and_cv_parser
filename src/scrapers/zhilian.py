"""
智联招聘 scraper (Playwright).
httpx returns a JS security-verification shell; Playwright renders the real page.
"""
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from .base import BaseScraper
from src.db import upsert_job

BASE       = "https://www.zhaopin.com"
SEARCH_URL = BASE + "/jobs?"

_LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]
_STEALTH     = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
_UA          = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_CHALLENGE_GONE = (
    "!document.title.includes('Verification') && "
    "!document.title.includes('Security') && "
    "!document.title.includes('Cloudflare') && "
    "document.title.length > 0"
)

# Selectors tried in order; first one with hits wins
_CARD_SELECTORS = [
    "li.job-list-item",
    "div.job-card",
    "a[class*='jobCard']",
    "div[class*='JobCard']",
    "li[class*='job']",
]
_TITLE_SELECTORS  = [".job-name", ".job-title", "h3 a", "h2 a", "a[class*='title']"]
_COMPANY_SELECTORS = [".company-name", ".corp-name", "a[class*='company']"]
_LOCATION_SELECTORS = [".job-area", ".work-area", "span[class*='city']"]


def _first_text(el, selectors: list[str]) -> str:
    for sel in selectors:
        found = el.select_one(sel)
        if found:
            return found.get_text(strip=True)
    return ""


class ZhilianScraper(BaseScraper):
    def scrape(self, keywords: list[str], city: str = "", max_pages: int = 3) -> int:
        added = 0
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=_LAUNCH_ARGS,
                ignore_default_args=["--enable-automation"],
            )
            ctx  = browser.new_context(user_agent=_UA)
            page = ctx.new_page()
            page.add_init_script(_STEALTH)

            for keyword in keywords:
                params: dict = {"kw": keyword, "pageSize": 30}
                if city:
                    params["cityCode"] = city

                for p in range(1, max_pages + 1):
                    params["pageNumber"] = p
                    url = SEARCH_URL + urlencode(params)
                    try:
                        page.goto(url, timeout=30_000, wait_until="domcontentloaded")
                        page.wait_for_function(_CHALLENGE_GONE, timeout=20_000)
                        page.wait_for_load_state("networkidle", timeout=10_000)
                    except PWTimeout:
                        print(f"  [zhilian] timeout p={p} kw='{keyword}' title='{page.title()}'")
                        break

                    soup  = BeautifulSoup(page.content(), "lxml")

                    # Auto-detect which card selector works on this page
                    cards = []
                    used_sel = ""
                    for sel in _CARD_SELECTORS:
                        cards = soup.select(sel)
                        if cards:
                            used_sel = sel
                            break

                    if not cards:
                        print(f"  [zhilian] 0 cards after load, title='{page.title()}'")
                        break

                    for card in cards:
                        try:
                            title    = _first_text(card, _TITLE_SELECTORS)
                            if not title:
                                continue
                            link_el  = card.select_one("a[href]")
                            href     = link_el.get("href", "") if link_el else ""
                            job_url  = href if href.startswith("http") else BASE + href
                            company  = _first_text(card, _COMPANY_SELECTORS)
                            location = _first_text(card, _LOCATION_SELECTORS)
                            desc_el  = card.select_one(".job-desc, .welfare-list, .job-detail-exp")
                            description = desc_el.get_text(" ", strip=True) if desc_el else ""
                            new_id   = upsert_job(
                                platform="zhilian",
                                title=title,
                                url=job_url,
                                company=company,
                                location=location,
                                description=description,
                            )
                            if new_id:
                                added += 1
                        except Exception:
                            continue
                    self._sleep()

            browser.close()
        return added
