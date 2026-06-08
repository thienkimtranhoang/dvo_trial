"""
Phase 2 Validate — Organisation
Validates Tavily search results to ensure they are actually about the organisation.
Uses heuristic first, LLM only for uncertain cases.
"""
import re
import sys
import os
import time
import json
import concurrent.futures
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import OLLAMA_URL, OLLAMA_MODEL

import requests


def ask_llm(prompt: str) -> str:
    for attempt in range(3):
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={
                    "model":    OLLAMA_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream":   False,
                    "options":  {"temperature": 0, "num_predict": 120},
                },
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
        except Exception:
            if attempt == 2:
                return ""
            time.sleep(2)
    return ""


ORG_KEYWORDS = [
    "founded", "established", "headquarters", "csr", "investment",
    "fund", "portfolio", "assets", "billion", "million", "real estate",
    "partnership", "donation", "scholarship", "charity", "award",
    "annual report", "sustainability", "board", "executive",
]


def _heuristic_validate(url: str, snippet: str, name: str) -> tuple:
    """Quick heuristic check — no LLM."""
    url_lower     = url.lower()
    snippet_lower = snippet.lower()
    name_lower    = name.lower()

    # Name parts — significant words only
    name_parts = [p for p in name_lower.split() if len(p) > 3 and p not in
                  ("pte", "ltd", "inc", "corp", "limited", "investments", "group")]

    # STRONG: full org name in URL
    name_slug  = name_lower.replace(" ", "-")
    name_slug2 = name_lower.replace(" ", "")
    name_in_url = (name_lower in url_lower or name_slug in url_lower or name_slug2 in url_lower)

    # STRONG: full org name in snippet (require full name match, not just parts)
    name_in_start   = name_lower in snippet_lower[:300]
    name_in_snippet = name_lower in snippet_lower

    # Support: org keywords
    has_org_kw = any(kw in snippet_lower for kw in ORG_KEYWORDS)

    if name_in_url and (name_in_start or name_in_snippet):
        return True, "high", f"[heuristic] org name in URL and snippet"
    if name_in_url or name_in_start:
        return True, "high", f"[heuristic] org name in URL or snippet start"
    if name_in_snippet and has_org_kw:
        return True, "medium", f"[heuristic] org name in snippet with keywords"
    if name_in_snippet:
        return None, "low", f"[heuristic] org name in snippet only"

    return False, "high", f"[heuristic] org name not found in URL or snippet"


def _build_validation_prompt(name: str, url: str, snippet: str) -> str:
    return f"""Is this search result actually about the specific organisation "{name}"?

URL: {url}
Snippet: {snippet[:500]}

Answer with a JSON object:
{{"valid": true/false, "confidence": "high/medium/low", "reason": "one sentence explanation"}}

Rules:
- Return true ONLY if the page is clearly about THIS SPECIFIC organisation named "{name}".
- Return false if it is about a DIFFERENT organisation that happens to have a similar name.
  Example: if searching for "Lotus Life Foundation", reject pages about "Lotus Health Foundation",
  "Lotus School Foundation", "Lotus Hope Foundation", "Lotus Petal Foundation" etc.
- Return false if the exact name "{name}" is not mentioned on the page.
- Be strict — similar names are NOT the same organisation.
- Return ONLY the JSON object, nothing else."""


def _parse_response(raw: str) -> tuple:
    try:
        raw = re.sub(r"```json|```", "", raw).strip()
        data = json.loads(raw)
        return data.get("valid", False), data.get("confidence", "low"), data.get("reason", "")
    except Exception:
        return None, "low", "could not parse LLM response"


def validate_result(r: dict, name: str) -> dict:
    """Validate a single search result."""
    url     = r.get("url", "")
    snippet = r.get("snippet") or r.get("content") or r.get("description") or ""

    # Heuristic first
    is_valid, confidence, reason = _heuristic_validate(url, snippet, name)

    # Only call LLM for uncertain cases
    if confidence in ("medium", "low") or is_valid is None:
        prompt = _build_validation_prompt(name, url, snippet)
        raw    = ask_llm(prompt)
        llm_valid, llm_conf, llm_reason = _parse_response(raw)
        if llm_reason != "could not parse LLM response":
            is_valid   = llm_valid
            confidence = llm_conf
            reason     = llm_reason

    return {**r, "_valid": bool(is_valid), "_confidence": confidence, "_reason": reason}


def run(results: list, name: str) -> tuple:
    """
    Validate all org search results in parallel.
    Returns (valid_results, rejected_results).
    """
    if not results:
        return [], []

    print(f"\n  [Org Validation] Checking {len(results)} results are about '{name}'...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(results))) as executor:
        validated = list(executor.map(lambda r: validate_result(r, name), results))

    valid    = [r for r in validated if r["_valid"]]
    rejected = [r for r in validated if not r["_valid"]]

    print(f"  [Org Validation] ✅ {len(valid)} valid, ❌ {len(rejected)} rejected")

    # Clean internal keys before returning
    for r in valid + rejected:
        r.pop("_valid",      None)
        r.pop("_confidence", None)
        r.pop("_reason",     None)

    return valid, rejected
