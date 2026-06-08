import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import re
import json
import concurrent.futures
import time
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import OLLAMA_URL, OLLAMA_MODEL

def ask_llm(prompt: str) -> str:
    import requests
    for attempt in range(3):
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={"model": OLLAMA_MODEL, "messages": [{"role": "user", "content": prompt}], "stream": False},
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
        except Exception:
            if attempt == 2: return ""
            time.sleep(2)
    return ""


# BIO KEYWORDS FOR HEURISTIC CHECK
BIO_KEYWORDS = [
    "born", "ceo", "founder", "chairman", "director", "president",
    "education", "net worth", "nationality", "university", "college",
    "billion", "million", "age", "studied", "graduated", "degree",
    "career", "appointed", "executive", "managing", "entrepreneur",
]

# HEURISTIC VALIDATION (no LLM)
def _heuristic_validate(url: str, snippet: str, name: str, company: str) -> tuple:
    snippet_lower = snippet.lower()
    url_lower     = url.lower()

    name_parts = [p for p in name.lower().split() if len(p) > 2]

    # STRONG: name parts in URL
    url_part_hits = sum(1 for p in name_parts if p in url_lower)
    name_slug     = name.lower().replace(" ", "_")
    name_slug2    = name.lower().replace(" ", "-")
    name_in_url   = name_slug in url_lower or name_slug2 in url_lower or url_part_hits >= 2

    # STRONG: name parts in start of snippet (first 150 chars)
    early_part_hits = sum(1 for p in name_parts if p in snippet_lower[:150])
    name_in_start   = name.lower() in snippet_lower[:150] or early_part_hits >= 2

    # MEDIUM: any name part anywhere in snippet
    snippet_part_hits = sum(1 for p in name_parts if p in snippet_lower)
    name_in_snippet   = snippet_part_hits >= 1

    # SUPPORT signals
    has_bio_kw  = any(kw in snippet_lower for kw in BIO_KEYWORDS)
    has_company = bool(company) and company.lower() in snippet_lower

    strong_signals  = sum([name_in_url, name_in_start])
    support_signals = sum([has_bio_kw, has_company])

    if strong_signals >= 1:
        is_valid   = True
        confidence = "high" if support_signals >= 1 else "medium"
    elif name_in_snippet and support_signals >= 1:
        is_valid   = True
        confidence = "medium"
    else:
        is_valid   = False
        confidence = "low"

    parts = []
    if name_in_url:     parts.append(f"name in URL ({url_part_hits} parts matched)")
    if name_in_start:   parts.append(f"name in snippet start ({early_part_hits} parts matched)")
    if name_in_snippet: parts.append(f"name in snippet ({snippet_part_hits} parts matched)")
    if has_bio_kw:      parts.append("bio keywords found")
    if has_company:     parts.append("company mentioned")
    if not parts:       parts.append(f"no name signals found (url hits: {url_part_hits}, snippet hits: {snippet_part_hits})")

    reason = "[heuristic] " + ", ".join(parts)
    return is_valid, confidence, reason


# VALIDATION PROMPT
def _build_validation_prompt(name: str, company: str, url: str, snippet: str) -> str:
    company_line = f"  - Known company/organisation: {company}" if company else ""
    return f"""You are checking whether a search result snippet is actually about a specific person.

Person we are researching:
  - Name: {name}
{company_line}

Source URL: {url}

Snippet:
{snippet}

Your job is to decide: does this snippet contain information actually about THIS specific person?

Rules:
- Return true ONLY if the snippet clearly refers to this specific individual (e.g. their career, biography, net worth, education, business dealings, awards, etc.)
- Return false if:
    * The snippet is about a DIFFERENT person who shares part of the name
    * The snippet is about a family member, ancestor, or relative — this does NOT count
    * The name appears only incidentally or in an unrelated context
    * The snippet is a generic list or directory with no specific information
    * The page is about a company/org and does NOT mention this person specifically

You MUST respond with ONLY this exact JSON on a single line, nothing else — no preamble, no explanation, no markdown, no backticks:
{{"is_valid": true, "confidence": "high", "reason": "your reason here"}}"""


# JSON PARSING WITH FALLBACKS
def _parse_validation_response(raw: str):
    cleaned = re.sub(r"```json|```", "", raw).strip()
    try:
        parsed     = json.loads(cleaned)
        is_valid   = bool(parsed.get("is_valid", False))
        confidence = parsed.get("confidence", "low")
        reason     = parsed.get("reason", "parsed ok")
        return is_valid, confidence, reason
    except Exception:
        pass

    match = re.search(r'\{[^{}]+\}', cleaned, re.DOTALL)
    if match:
        try:
            parsed     = json.loads(match.group())
            is_valid   = bool(parsed.get("is_valid", False))
            confidence = parsed.get("confidence", "low")
            reason     = parsed.get("reason", "extracted from partial JSON")
            return is_valid, confidence, reason
        except Exception:
            pass

    lower = raw.lower()
    if '"is_valid": true' in lower or '"is_valid":true' in lower:
        return True, "medium", "keyword fallback: is_valid true found in response"
    if '"is_valid": false' in lower or '"is_valid":false' in lower:
        return False, "medium", "keyword fallback: is_valid false found in response"

    return False, "low", "could not parse LLM response"


# PER-URL VALIDATION (validates once per unique URL)
def _validate_url(url: str, snippet: str, name: str, company: str) -> dict:
    """
    Validates a single unique URL. Returns a validation result dict
    with keys: _valid, _confidence, _val_reason, _val_method.
    """
    prompt = _build_validation_prompt(name, company, url, snippet)

    # Attempt 1: LLM
    raw = ask_llm(prompt)
    is_valid, confidence, reason = _parse_validation_response(raw)
    method = "llm"

    # Attempt 2: Heuristic fallback (no retry -- 60+ results, too slow)
    if reason == "could not parse LLM response":
        print(f"    [Validation] LLM parse failed -- falling back to heuristic for {url[:60]}...")
        is_valid, confidence, reason = _heuristic_validate(url, snippet, name, company)
        method = "heuristic"

    return {
        "_valid":      is_valid,
        "_confidence": confidence,
        "_val_reason": reason,
        "_val_method": method,
    }


# BATCH VALIDATION ENTRYPOINT
def run(results: list, name: str, company: str = "") -> tuple:
    """
    Validates all search results in parallel, deduplicating by URL so each
    URL is only validated once even if it appears across multiple attributes.

    Input:  list[list[dict]] or list[dict] — each item has 'url', 'snippet', 'attribute'
    Returns: (valid_results, rejected_results)
    """
    if not results:
        return [], []

    # Flatten nested list structure from phase_2_search
    flat_results = []
    for item in results:
        if isinstance(item, list):
            for sub_item in item:
                if isinstance(sub_item, dict):
                    flat_results.append(sub_item)
        elif isinstance(item, dict):
            flat_results.append(item)

    if not flat_results:
        print("  [Validation] No items found after flattening.")
        return [], []

    # Deduplicate by URL — keep one representative item per URL for validation
    # but track ALL items (with all their attributes) so we can re-attach later
    url_to_items  = {}   # url -> list of all result dicts sharing that url
    url_to_sample = {}   # url -> one representative dict (for validation)
    for item in flat_results:
        url = item.get("url", "")
        if url not in url_to_items:
            url_to_items[url]  = []
            url_to_sample[url] = item   # use first occurrence as representative
        url_to_items[url].append(item)

    unique_urls = list(url_to_sample.keys())
    saved = len(flat_results) - len(unique_urls)
    print(f"\n  [Validation] {len(flat_results)} results -> {len(unique_urls)} unique URLs "
          f"({saved} duplicate URL validations skipped)")

    # Validate each unique URL once in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(unique_urls), 20)) as executor:
        val_results = list(executor.map(
            lambda url: (url, _validate_url(url, url_to_sample[url].get("snippet", ""), name, company)),
            unique_urls
        ))

    # Build a cache: url -> validation result dict
    url_cache = {url: val for url, val in val_results}

    # Re-attach validation result to every original item (including duplicates)
    validated_flat = []
    for item in flat_results:
        url = item.get("url", "")
        val = url_cache.get(url, {"_valid": False, "_confidence": "low",
                                  "_val_reason": "no cache hit", "_val_method": "heuristic"})
        validated_flat.append({**item, **val})

    # Print summary
    print(f"\n{'='*75}")
    print(f"  VALIDATION RESULTS")
    print(f"{'='*75}")

    # Print one line per unique URL (not per result, to avoid duplicates in output)
    printed_urls  = set()
    valid_results    = []
    rejected_results = []

    for r in validated_flat:
        url = r.get("url", "")
        if url not in printed_urls:
            status = "✓ VALID   " if r["_valid"] else "✗ REJECTED"
            conf   = r["_confidence"].upper()
            reason = r["_val_reason"]
            method = r.get("_val_method", "llm").upper()
            attrs  = ", ".join(i.get("attribute", "") for i in url_to_items[url])
            print(f"  {status} [{conf:6s}] [{method:9s}] {url}")
            print(f"             -> {reason}")
            print(f"             -> attributes: [{attrs}]")
            printed_urls.add(url)

        if r["_valid"]:
            valid_results.append(r)
        else:
            rejected_results.append(r)

    llm_count       = sum(1 for url, val in url_cache.items() if val.get("_val_method") == "llm")
    heuristic_count = sum(1 for url, val in url_cache.items() if val.get("_val_method") == "heuristic")
    print(f"\n  Summary : {len(valid_results)} valid, {len(rejected_results)} rejected "
          f"(from {len(validated_flat)} total, {len(unique_urls)} unique URLs validated)")
    print(f"  Methods : {llm_count} via LLM, {heuristic_count} via heuristic fallback")

    # Safety net
    if not valid_results and rejected_results:
        salvageable = [r for r in rejected_results if r["_confidence"] in ("high", "medium")]
        if salvageable:
            print(f"\n  WARNING: All results rejected -- salvaging {len(salvageable)} medium/high-confidence results")
            valid_results    = salvageable
            rejected_results = [r for r in rejected_results if r not in salvageable]

    print(f"{'='*75}")
    return valid_results, rejected_results