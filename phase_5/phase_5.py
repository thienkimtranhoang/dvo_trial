"""
Phase 5 — Post-processing
Cleans shallow attributes (age, DOB, nationality, education, net worth) from biography.
"""
import re
import time
import requests
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import OLLAMA_URL, OLLAMA_MODEL


def ask_llm(prompt: str, num_predict: int = 1000) -> str:
    for attempt in range(3):
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={
                    "model":    OLLAMA_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream":   False,
                    "options":  {"temperature": 0, "num_predict": num_predict},
                },
                timeout=180,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
        except Exception:
            if attempt == 2:
                return ""
            time.sleep(3)
    return ""


def clean_biography(results: dict, name: str) -> dict:
    """Remove shallow attributes from biography — they appear in header fields."""
    bio_data = results.get("BIOGRAPHY", {})
    bio_text = bio_data.get("content", "")
    if not bio_text:
        return results

    prompt = f"""Edit this biography of {name}.

Current biography:
{bio_text}

Remove ALL of the following from the text:
- Any mention of age, date of birth, birth year, or being born in a specific place
- Any mention of nationality, country of origin, hometown, or province
- Any mention of education, degree, university, school, maritime institute, or graduation
- Any mention of personal net worth, personal wealth, or estimated wealth figures
- Sentences like "He is a Chinese national", "He was born in Shandong", "with a background in maritime studies"

Keep everything else intact including inline citations [[N]].
After removing, make sure the remaining text flows naturally as a paragraph.
Return ONLY the cleaned biography text, no headers, no explanation."""

    cleaned = ask_llm(prompt, num_predict=1500)
    if cleaned:
        results["BIOGRAPHY"]["content"] = cleaned
        print(f"  ✅ Biography cleaned")
    return results


def run(phase4_output: dict) -> dict:
    """Phase 5: clean shallow attributes from biography."""
    name    = phase4_output.get("name", "")
    results = phase4_output.get("results", {})
    results = clean_biography(results, name)
    return {
        "name":    name,
        "company": phase4_output.get("company", ""),
        "results": results,
    }
