"""
PhD-Seeker scraper for academic PhD positions (scholarshipdb.net + findaphd.com).
Uses PhDSeeker Python API directly.
"""
from .base import BaseScraper
from src.db import upsert_job


class PhDSeekerScraper(BaseScraper):
    def scrape(
        self,
        keywords: list[str],
        country: str = "",
        max_pages: int = 3,
    ) -> int:
        from phdseeker.main import PhDSeeker

        added = 0
        # PhDSeeker expects a single comma-separated keyword string
        kw_str = ", ".join(keywords)

        try:
            ps = PhDSeeker(
                keywords=kw_str,
                maxpage=max_pages,
                desired_countries=country if country else None,
            )
            df = ps.positions

            if df is None or df.empty:
                print(f"  [phdseeker] 0 results for '{kw_str}'")
                return 0

            print(f"  [phdseeker] '{kw_str}' → {len(df)} fetched")

            for _, row in df.iterrows():
                try:
                    title = str(row.get("Title") or "").strip()
                    if not title:
                        continue
                    new_id = upsert_job(
                        platform="phdseeker",
                        title=title,
                        url=str(row.get("Link") or ""),
                        company="",
                        location=str(row.get("Country") or ""),
                        description="",
                    )
                    if new_id:
                        added += 1
                except Exception:
                    continue

        except Exception as e:
            print(f"  [phdseeker] error: {e}")

        return added
