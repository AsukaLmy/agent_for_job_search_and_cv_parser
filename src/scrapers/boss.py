"""
Boss直聘 scraper using Playwright.

First run: opens a visible browser for the user to log in manually.
After login the cookies are saved to data/boss_cookies.json.
Subsequent runs reuse saved cookies in headless mode.
"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from .base import BaseScraper
from src.db import upsert_job

COOKIES_FILE = Path(__file__).parent.parent.parent / "data" / "boss_cookies.json"
BASE_URL     = "https://www.zhipin.com"
SEARCH_URL   = BASE_URL + "/web/geek/job?query={query}&city=100010000"  # 100010000 = 全国


class BossScraper(BaseScraper):
    def _load_cookies(self) -> list | None:
        if COOKIES_FILE.exists():
            return json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
        return None

    def _save_cookies(self, cookies: list) -> None:
        COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        COOKIES_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")

    def _login_interactively(self, playwright) -> list:
        """Open a visible browser, wait for user to log in, then return cookies."""
        browser = playwright.chromium.launch(headless=False)
        ctx     = browser.new_context()
        page    = ctx.new_page()
        page.goto(BASE_URL + "/web/user/?ka=header-login")
        print("\n[Boss直聘] 请在浏览器中手动完成登录，登录后脚本将自动继续...")
        # Wait until the user is on the job-search page (login succeeded)
        try:
            page.wait_for_url("**/web/geek/**", timeout=120_000)
        except PWTimeout:
            page.wait_for_timeout(5000)
        cookies = ctx.cookies()
        browser.close()
        return cookies

    def scrape(self, keywords: list[str], city: str = "全国", max_pages: int = 3) -> int:
        added = 0
        with sync_playwright() as pw:
            cookies = self._load_cookies()
            if not cookies:
                cookies = self._login_interactively(pw)
                self._save_cookies(cookies)

            browser = pw.chromium.launch(headless=True)
            ctx     = browser.new_context()
            ctx.add_cookies(cookies)
            page    = ctx.new_page()

            for keyword in keywords:
                for p in range(1, max_pages + 1):
                    url = SEARCH_URL.format(query=keyword) + f"&page={p}"
                    try:
                        page.goto(url, timeout=30_000)
                        page.wait_for_selector("ul.job-list-box li.job-card-wrapper", timeout=15_000)
                    except PWTimeout:
                        break

                    cards = page.query_selector_all("li.job-card-wrapper")
                    if not cards:
                        break

                    for card in cards:
                        try:
                            title    = card.query_selector(".job-name").inner_text().strip()
                            company  = card.query_selector(".company-name").inner_text().strip()
                            loc_el   = card.query_selector(".job-area")
                            location = loc_el.inner_text().strip() if loc_el else ""
                            link_el  = card.query_selector("a.job-card-left")
                            href     = link_el.get_attribute("href") if link_el else ""
                            job_url  = BASE_URL + href if href.startswith("/") else href
                            desc_el  = card.query_selector(".job-desc")
                            description = desc_el.inner_text().strip() if desc_el else ""
                            new_id   = upsert_job(
                                platform="boss",
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

    def open_job_page(self, url: str) -> None:
        """Open a job page in a visible browser for the user to interact with."""
        with sync_playwright() as pw:
            cookies = self._load_cookies()
            browser = pw.chromium.launch(headless=False)
            ctx     = browser.new_context()
            if cookies:
                ctx.add_cookies(cookies)
            page = ctx.new_page()
            page.goto(url, timeout=30_000)
            print("[Boss直聘] 已打开职位页面。按 Enter 键关闭浏览器，或直接在浏览器中操作...")
            input()
            browser.close()
