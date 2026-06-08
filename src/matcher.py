"""
Job–resume matcher using DeepSeek API.
Scores each unscored job 0–100 and extracts matched/missing skills.
"""
import json
import os
import time
from typing import Any

from openai import OpenAI

from src.db import get_unscored, update_match
from src.parser import load_resume, DEEPSEEK_BASE_URL

SYSTEM_PROMPT = """You are a recruitment expert. Given a resume and a job description,
evaluate how well the candidate fits the role.

Return ONLY a JSON object (no markdown, no explanation):
{
  "score": <integer 0-100>,
  "matched_skills": ["skill1", "skill2"],
  "missing_skills": ["skill3"],
  "summary": "<1-2 sentence assessment in the same language as the job posting>"
}

Scoring guide:
- 90–100: Excellent match, meets all requirements
- 70–89:  Good match, meets most requirements
- 50–69:  Partial match, significant gaps
- 0–49:   Poor fit"""


def match_jobs(
    api_key: str = "",
    model: str = "deepseek-v4-flash",
    limit: int = 50,
    min_score: int = 0,
    api_delay: float = 1.0,
) -> list[dict]:
    """Score unscored jobs and return rows with score >= min_score."""
    resume = load_resume()
    resume_text = json.dumps(resume, ensure_ascii=False)

    key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise ValueError("DEEPSEEK_API_KEY not set.")

    client  = OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)
    jobs    = get_unscored(limit=limit)
    total   = len(jobs)
    results = []

    for idx, job in enumerate(jobs, 1):
        print(f"  [{idx}/{total}] {job['platform']:10s}  {job['title'][:40]}", flush=True)
        job_text = (
            f"Title: {job['title']}\n"
            f"Company/Institution: {job['company']}\n"
            f"Location: {job['location']}\n"
            f"Description:\n{job['description']}"
        )
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=2048,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"RESUME:\n{resume_text}\n\nJOB POSTING:\n{job_text}"},
                ],
                reasoning_effort="high",
                extra_body={"thinking": {"type": "enabled"}},
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data: dict[str, Any] = json.loads(raw)
        except Exception as e:
            data = {"score": 0, "matched_skills": [], "missing_skills": [], "summary": f"Error: {e}"}

        score = int(data.get("score", 0))
        update_match(job["id"], score, json.dumps(data, ensure_ascii=False))
        print(f"         → 分数: {score}  {data.get('summary', '')}", flush=True)

        if score >= min_score:
            results.append({**dict(job), **data})

        if idx < total and api_delay > 0:
            time.sleep(api_delay)

    return results
