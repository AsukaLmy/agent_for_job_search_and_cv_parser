import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "jobs.db"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                platform    TEXT NOT NULL,
                title       TEXT NOT NULL,
                company     TEXT,
                location    TEXT,
                url         TEXT UNIQUE NOT NULL,
                description TEXT,
                posted_date TEXT,
                match_score INTEGER,
                match_data  TEXT,   -- JSON: matched_skills, missing_skills, summary
                status      TEXT DEFAULT 'new',  -- new | matched | submitted | skipped
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_platform ON jobs(platform)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status   ON jobs(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_score    ON jobs(match_score)")


def upsert_job(
    platform: str,
    title: str,
    url: str,
    company: str = "",
    location: str = "",
    description: str = "",
    posted_date: str = "",
) -> Optional[int]:
    """Insert a new job; skip silently if URL already exists. Returns new row id or None."""
    with get_conn() as conn:
        try:
            cur = conn.execute(
                """INSERT INTO jobs (platform, title, company, location, url, description, posted_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (platform, title, company, location, url, description, posted_date),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def update_match(job_id: int, score: int, match_data: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE jobs SET match_score=?, match_data=?, status='matched' WHERE id=?",
            (score, match_data, job_id),
        )


def update_status(job_id: int, status: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))


def get_unscored(limit: int = 50) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM jobs WHERE match_score IS NULL ORDER BY id LIMIT ?", (limit,)
        ).fetchall()


def get_top_jobs(n: int = 30, min_score: int = 0) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM jobs WHERE match_score IS NOT NULL AND match_score >= ?"
            " ORDER BY match_score DESC LIMIT ?",
            (min_score, n),
        ).fetchall()


def get_matched(min_score: int = 60) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM jobs WHERE match_score >= ? AND status='matched' ORDER BY match_score DESC",
            (min_score,),
        ).fetchall()


def stats() -> dict:
    with get_conn() as conn:
        total   = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        by_plat = conn.execute(
            "SELECT platform, COUNT(*) as n FROM jobs GROUP BY platform"
        ).fetchall()
        scored  = conn.execute("SELECT COUNT(*) FROM jobs WHERE match_score IS NOT NULL").fetchone()[0]
        return {"total": total, "scored": scored, "by_platform": {r["platform"]: r["n"] for r in by_plat}}
