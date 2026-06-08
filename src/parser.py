"""
Resume parser: extracts text from PDF then uses DeepSeek API to produce structured JSON.
"""
import json
import os
from pathlib import Path

import fitz  # PyMuPDF
from openai import OpenAI

RESUME_JSON = Path(__file__).parent.parent / "data" / "resume.json"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

SYSTEM_PROMPT = """You are a resume parser. Extract all information from the resume text
and return ONLY a valid JSON object with this exact schema (no markdown, no explanation):
{
  "name": "",
  "email": "",
  "phone": "",
  "location": "",
  "summary": "",
  "education": [
    {"degree": "", "field": "", "institution": "", "year_start": "", "year_end": "", "gpa": ""}
  ],
  "experience": [
    {"title": "", "company": "", "location": "", "start": "", "end": "", "description": ""}
  ],
  "skills": [],
  "languages": [{"language": "", "proficiency": ""}],
  "publications": [{"title": "", "venue": "", "year": ""}],
  "awards": [],
  "links": {"github": "", "linkedin": "", "website": ""}
}
Fill every field you can find. Use empty string or empty list for missing fields. Never add extra keys."""


def extract_text_from_pdf(pdf_path: Path) -> str:
    doc = fitz.open(pdf_path)
    pages = [page.get_text() for page in doc]
    return "\n".join(pages)


def find_resume_pdf(resume_dir: Path) -> Path:
    pdfs = sorted(resume_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDF found in {resume_dir}. Put your resume there.")
    return pdfs[0]


def parse_resume(resume_dir: Path, api_key: str = "", model: str = "deepseek-v4-flash", force: bool = False) -> dict:
    """Parse resume PDF and return structured dict. Caches result to data/resume.json."""
    if RESUME_JSON.exists() and not force:
        return json.loads(RESUME_JSON.read_text(encoding="utf-8"))

    pdf_path = find_resume_pdf(resume_dir)
    raw_text = extract_text_from_pdf(pdf_path)

    key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise ValueError("DEEPSEEK_API_KEY not set. Add it to .env or set the environment variable.")

    client = OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)
    response = client.chat.completions.create(
        model=model,
        max_tokens=2048,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Parse this resume:\n\n{raw_text}"},
        ],
        extra_body={"thinking": {"type": "disabled"}},
    )

    raw_json = response.choices[0].message.content.strip()
    # Strip markdown fences if model wrapped output
    if raw_json.startswith("```"):
        raw_json = raw_json.split("```")[1]
        if raw_json.startswith("json"):
            raw_json = raw_json[4:]

    data = json.loads(raw_json)
    RESUME_JSON.parent.mkdir(parents=True, exist_ok=True)
    RESUME_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def load_resume() -> dict:
    if not RESUME_JSON.exists():
        raise FileNotFoundError("Resume not parsed yet. Run: python main.py parse")
    return json.loads(RESUME_JSON.read_text(encoding="utf-8"))
