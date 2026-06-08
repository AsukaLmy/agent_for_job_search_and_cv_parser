"""
JobSpy scraper for international job boards (LinkedIn, Indeed, Glassdoor, etc.)
"""
from .base import BaseScraper
from src.db import upsert_job

DEFAULT_SITES = ["linkedin", "indeed", "glassdoor"]


class JobSpyScraper(BaseScraper):
    def scrape(
        self,
        keywords: list[str],
        location: str = "",
        max_results: int = 50,
        sites: list[str] | None = None,
    ) -> int:
        from jobspy import scrape_jobs

        added = 0
        target_sites = sites or DEFAULT_SITES

        for keyword in keywords:
            try:
                jobs = scrape_jobs(
                    site_name=target_sites,
                    search_term=keyword,
                    location=location,
                    results_wanted=max_results,
                    hours_old=168,  # Last 7 days
                )
                if jobs is None or jobs.empty:
                    print(f"  [jobspy] 0 results for '{keyword}'")
                    continue

                for _, row in jobs.iterrows():
                    try:
                        title = str(row.get("title") or "").strip()
                        if not title:
                            continue
                        site = str(row.get("site") or "unknown")
                        new_id = upsert_job(
                            platform=f"jobspy_{site}",
                            title=title,
                            url=str(row.get("job_url") or ""),
                            company=str(row.get("company") or ""),
                            location=str(row.get("location") or ""),
                            description=str(row.get("description") or ""),
                        )
                        if new_id:
                            added += 1
                    except Exception:
                        continue

                print(f"  [jobspy] '{keyword}' → {len(jobs)} fetched")
                self._sleep()
            except Exception as e:
                print(f"  [jobspy] error for '{keyword}': {e}")
                continue

        return added
