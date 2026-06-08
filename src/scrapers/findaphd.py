"""
FindAPhD.com scraper (Playwright).
Playwright executes JavaScript and can pass Cloudflare's basic JS challenge.
"""
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from .base import BaseScraper
from src.db import upsert_job

BASE       = "https://www.findaphd.com"
SEARCH_URL = BASE + "/phds/?"

_LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]
_STEALTH     = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
_UA          = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
# Wait until the page is no longer a Cloudflare challenge page
_CHALLENGE_GONE = (
    "!document.title.includes('moment') && "
    "!document.title.includes('Cloudflare') && "
    "!document.title.includes('Verification') && "
    "document.title.length > 0"
)


class FindAPhDScraper(BaseScraper):
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
                params: dict = {"Keywords": keyword, "PhdFullTime": 1, "PhdPartTime": 1}
                if country:
                    params["CountryCode"] = country

                for p in range(1, max_pages + 1):
                    params["PageNumber"] = p
                    url = SEARCH_URL + urlencode(params)
                    try:
                        page.goto(url, timeout=30_000, wait_until="domcontentloaded")
                        # Let Cloudflare challenge resolve (up to 20 s)
                        page.wait_for_function(_CHALLENGE_GONE, timeout=20_000)
                        page.wait_for_load_state("networkidle", timeout=10_000)
                    except PWTimeout:
                        print(f"  [FindAPhD] timeout p={p} kw='{keyword}' title='{page.title()}'")
                        break

                    soup    = BeautifulSoup(page.content(), "lxml")
                    results = soup.select("div.phd-result")
                    if not results:
                        print(f"  [FindAPhD] 0 cards after load, title='{page.title()}'")
                        break

                    for card in results:
                        try:
                            title_el = card.select_one("h3 a, h4 a")
                            if not title_el:
                                continue
                            title    = title_el.get_text(strip=True)
                            href     = title_el.get("href", "")
                            job_url  = BASE + href if href.startswith("/") else href
                            inst_el  = card.select_one(".phd-result__dept, .institution")
                            institution = inst_el.get_text(strip=True) if inst_el else ""
                            loc_el   = card.select_one(".phd-result__key-info, .location")
                            location = loc_el.get_text(strip=True) if loc_el else ""
                            desc_el  = card.select_one(".phd-result__description, .description")
                            description = desc_el.get_text(" ", strip=True) if desc_el else ""
                            new_id   = upsert_job(
                                platform="findaphd",
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
