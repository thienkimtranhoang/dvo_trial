"""
Phase 4 Extract — Extracts shallow attributes from Phase 4 biography.
If fields are missing they will be filled by Phase 1.
"""
import re
import json
import time
import requests
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import OLLAMA_URL, OLLAMA_MODEL


def ask_llm(prompt: str) -> str:
    for attempt in range(3):
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={
                    "model":    OLLAMA_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream":   False,
                    "options":  {"temperature": 0, "num_predict": 300},
                },
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
        except Exception:
            if attempt == 2:
                return ""
            time.sleep(3)
    return ""


def clean_text(text: str) -> str:
    """Remove control characters and normalize whitespace."""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def parse_json_safe(raw: str) -> dict:
    """Try multiple approaches to parse JSON from LLM response."""
    raw = re.sub(r'```json|```', '', raw).strip()
    raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw)

    # Try direct parse
    try:
        return json.loads(raw)
    except Exception:
        pass

    # Try extracting just the JSON object
    m = re.search(r'\{.*?\}', raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass

    # Try fixing unescaped newlines inside strings
    try:
        fixed = re.sub(r'(?<!\\)\n', ' ', raw)
        return json.loads(fixed)
    except Exception:
        pass

    return {}


def extract_shallow(biography: str, name: str, bio_sources: list) -> dict:
    """Extract age, nationality, net worth, education from biography."""
    if not biography:
        return {"age": None, "nationality": None, "net_worth": None, "education": []}

    # Clean biography before sending
    bio_clean = clean_text(biography)
    # Truncate to avoid token limits
    bio_short = bio_clean[:1500]

    prompt = f"""Extract facts about {name} from this biography text.

Text: {bio_short}

Return ONLY this JSON with short simple values:
{{
  "age": integer or null,
  "net_worth": "$X Billion" or null,
  "education": [{{"degree": "degree name", "institution": "university name"}}] or [],
  "age_source_num": integer or null,
  "net_worth_source_num": integer or null,
  "education_source_num": integer or null
}}

Rules:
- age: integer only e.g. 62. Calculate from birth year if mentioned.
- net_worth: PERSONAL wealth only. Extract the EXACT dollar figure written in the text e.g. "$2.8 Billion". NEVER return a placeholder like "$X Billion" — if no real number found return null.
- education: full formal degree name and full university name.
- source_num: the [[N]] citation number next to where each field was mentioned, or null.
- Return ONLY the JSON, nothing else."""

    raw    = ask_llm(prompt)
    result = parse_json_safe(raw)

    def get_source_url(num):
        if num and isinstance(num, int) and 1 <= num <= len(bio_sources):
            return bio_sources[num - 1]
        if bio_sources:
            return bio_sources[0]
        return None

    return {
        "age":               result.get("age"),
        "age_source":        get_source_url(result.get("age_source_num")),
        "net_worth":         result.get("net_worth"),
        "nw_source":         get_source_url(result.get("net_worth_source_num")),
        "nw_year":           None,
        "education":         result.get("education", []),
        "edu_source":        get_source_url(result.get("education_source_num")),
    }


def run(phase4_results: dict, name: str) -> tuple:
    print(f"\n  Extracting shallow attributes from Phase 4 biography...")

    bio_data   = phase4_results.get("BIOGRAPHY", {})
    bio_text   = bio_data.get("content", "")
    bio_sources = bio_data.get("sources", [])

    # Normalize sources to list of URL strings
    src_urls = []
    for s in bio_sources:
        if isinstance(s, dict):
            src_urls.append(s.get("url", ""))
        elif isinstance(s, str):
            src_urls.append(s)

    extracted = extract_shallow(bio_text, name, src_urls)

    found   = [f for f in ["age", "net_worth", "education"] if extracted.get(f) and extracted.get(f) != []]
    missing = [f for f in ["age", "net_worth", "education"] if not extracted.get(f) or extracted.get(f) == []]

    print(f"    Found    : {found if found else 'nothing'}")
    print(f"    Missing  : {missing if missing else 'nothing'}")
    print(f"    Note     : nationality always from Phase 1")
    if extracted.get("age"):       print(f"    age        : {extracted['age']}")
    if extracted.get("net_worth"): print(f"    net_worth  : {extracted['net_worth']}")
    if extracted.get("education"): print(f"    education  : {extracted['education']}")

    shallow = {**extracted, "name": name}
    return shallow, phase4_results
