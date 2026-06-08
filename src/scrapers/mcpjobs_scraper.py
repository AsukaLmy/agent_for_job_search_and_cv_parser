"""
mcp-jobs scraper for Chinese job platforms (Boss直聘, 智联, 51job, 猎聘).
Spawns the locally-installed mcp-jobs MCP server via Node.js and calls its tools.
Requires Node.js >= 16.  Run `npm install mcp-jobs` in the project root first.

Data note: mcp-jobs returns structured fields (title/company/address/salary/tags/jobDetail)
when CSS selectors match, or falls back to {content: "..."} when they don't.
Both formats are handled here.
"""
import asyncio
import hashlib
import json
import re
from pathlib import Path

from .base import BaseScraper
from src.db import upsert_job

# Project root is three directories up from this file (src/scrapers/mcpjobs_scraper.py)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_MCP_JOBS_JS  = _PROJECT_ROOT / "node_modules" / "mcp-jobs" / "dist" / "mcp.js"

# Split content string at common Chinese job-listing delimiters to extract title
_TITLE_SPLIT = re.compile(r'【|薪资|薪酬|\d+[kK万]|\s{2,}')


def _parse_job(job: dict, fallback_city: str) -> dict | None:
    """Return normalised job dict or None if unusable."""
    title = str(job.get("title") or "").strip()
    content = str(job.get("content") or "").strip()

    if not title:
        if not content:
            return None
        # Extract title from beginning of content up to a delimiter
        m = _TITLE_SPLIT.search(content)
        title = content[: m.start()].strip() if m else content[:40].strip()
        if not title:
            return None

    url = str(job.get("jobDetail") or job.get("url") or "").strip()
    if not url:
        # Stable unique identifier derived from content so duplicates are deduped
        url = "mcpjobs://" + hashlib.md5((title + content).encode()).hexdigest()

    # Build description from structured fields or raw content
    if content:
        description = content
    else:
        salary = str(job.get("salary") or "")
        tags = job.get("tags", [])
        if isinstance(tags, list):
            tags = " ".join(t for t in tags if t)
        description = " | ".join(p for p in [salary, tags] if p)

    return {
        "title": title,
        "url": url,
        "company": str(job.get("company") or ""),
        "location": str(job.get("address") or fallback_city),
        "description": description,
    }


class MCPJobsScraper(BaseScraper):
    def scrape(
        self,
        keywords: list[str],
        city: str = "",
        max_pages: int = 3,
    ) -> int:
        if not _MCP_JOBS_JS.exists():
            print(f"  [mcpjobs] mcp-jobs not found at {_MCP_JOBS_JS}")
            print("  [mcpjobs] Run: npm install mcp-jobs  in the project root")
            return 0
        return asyncio.run(self._async_scrape(keywords, city, max_pages))

    async def _async_scrape(
        self,
        keywords: list[str],
        city: str,
        max_pages: int,
    ) -> int:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        added = 0
        server_params = StdioServerParameters(
            command="node",
            args=[str(_MCP_JOBS_JS)],
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                for keyword in keywords:
                    for page in range(1, max_pages + 1):
                        try:
                            # Always pass city (even as "") to avoid JS undefined concatenation bug
                            params: dict = {"keyword": keyword, "page": page, "city": city}

                            result = await session.call_tool("mcp_search_job", params)
                            raw = result.content[0].text if result.content else "{}"
                            data = json.loads(raw)
                            jobs = data.get("jobs", [])

                            if not jobs:
                                print(f"  [mcpjobs] 0 jobs p={page} kw='{keyword}'")
                                break

                            page_added = 0
                            for job in jobs:
                                parsed = _parse_job(job, city)
                                if parsed is None:
                                    continue
                                try:
                                    new_id = upsert_job(
                                        platform="mcpjobs",
                                        **parsed,
                                    )
                                    if new_id:
                                        page_added += 1
                                except Exception:
                                    continue

                            added += page_added
                            print(f"  [mcpjobs] '{keyword}' p={page} → {len(jobs)} found, {page_added} new")

                        except Exception as e:
                            print(f"  [mcpjobs] error kw='{keyword}' p={page}: {e}")
                            break

        return added
