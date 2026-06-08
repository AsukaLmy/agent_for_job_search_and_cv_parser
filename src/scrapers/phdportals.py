"""
PhDPortals.eu scraper (Playwright).
Playwright executes JavaScript and can pass Cloudflare's basic JS challenge.
"""
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from .base import BaseScraper
from src.db import upsert_job

BASE       = "https://www.phdportal.eu"
SEARCH_URL = BASE + "/search/"

_LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]
_STEALTH     = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
_UA          = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_CHALLENGE_GONE = (
    "!document.title.includes('moment') && "
    "!document.title.includes('Cloudflare') && "
    "!document.title.includes('Attention Required') && "
    "!document.title.includes('Verification') && "
    "document.title.length > 0"
)


class PhDPortalsScraper(BaseScraper):
    def scrape(self, keywords: list[str], country: str = "", max_pages: int = 3) -> int:
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
                params: dict = {"q": keyword, "degree": "phd"}
                if country:
                    params["country"] = country

                for p in range(1, max_pages + 1):
                    params["page"] = p
                    url = SEARCH_URL + "?" + urlencode(params)
                    try:
                        page.goto(url, timeout=30_000, wait_until="domcontentloaded")
                        page.wait_for_function(_CHALLENGE_GONE, timeout=20_000)
                        page.wait_for_load_state("networkidle", timeout=10_000)
                    except PWTimeout:
                        print(f"  [PhDPortals] timeout p={p} kw='{keyword}' title='{page.title()}'")
                        break

                    soup  = BeautifulSoup(page.content(), "lxml")
                    cards = soup.select("article.course-card, div.programme-card")
                    if not cards:
                        print(f"  [PhDPortals] 0 cards after load, title='{page.title()}'")
                        break

                    for card in cards:
                        try:
                            title_el = card.select_one("h3 a, h2 a, .programme-title a")
                            if not title_el:
                                continue
                            title       = title_el.get_text(strip=True)
                            href        = title_el.get("href", "")
                            job_url     = urljoin(BASE, href)
                            inst_el     = card.select_one(".university-name, .institution")
                            institution = inst_el.get_text(strip=True) if inst_el else ""
                            loc_el      = card.select_one(".country, .location")
                            location    = loc_el.get_text(strip=True) if loc_el else ""
                            desc_el     = card.select_one(".description, .programme-description")
                            description = desc_el.get_text(" ", strip=True) if desc_el else ""
                            new_id = upsert_job(
                                platform="phdportals",
                                title=title,
                                url=job_url,
                                company=institution,
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
