import re
import json
import concurrent.futures
import time
from phase_2_utils import ask_llm, ask_llm_validate

# BIO KEYWORDS FOR HEURISTIC CHECK
BIO_KEYWORDS = [
    "born", "ceo", "founder", "chairman", "director", "president",
    "education", "net worth", "nationality", "university", "college",
    "billion", "million", "age", "studied", "graduated", "degree",
    "career", "appointed", "executive", "managing", "entrepreneur",
]

FALLBACK_REASONS = {"could not parse LLM response", "empty LLM response"}

# ─────────────────────────────────────────────────────────────────────────────
# HEURISTIC VALIDATION
# ─────────────────────────────────────────────────────────────────────────────
def _heuristic_validate(url: str, snippet: str, name: str, company: str) -> tuple:
    snippet_lower = snippet.lower()
    url_lower     = url.lower()

    name_parts   = [p for p in name.lower().split() if len(p) > 2]
    weak_parts   = [p for p in name_parts if len(p) <= 4]
    strong_parts = [p for p in name_parts if len(p) > 4]

    # URL signals
    url_part_hits = sum(1 for p in name_parts if p in url_lower)
    name_slug     = name.lower().replace(" ", "_")
    name_slug2    = name.lower().replace(" ", "-")
    name_in_url   = name_slug in url_lower or name_slug2 in url_lower or url_part_hits >= 2

    # Snippet start signal
    early_part_hits = sum(1 for p in name_parts if p in snippet_lower[:150])
    name_in_start   = name.lower() in snippet_lower[:150] or early_part_hits >= 2

    # Full name match (forward + reversed)
    reversed_name   = " ".join(reversed(name.lower().split()))
    full_name_match = name.lower() in snippet_lower or reversed_name in snippet_lower

    # Snippet part hits
    weak_hits   = sum(1 for p in weak_parts   if p in snippet_lower)
    strong_hits = sum(1 for p in strong_parts if p in snippet_lower)

    name_in_snippet = (
        strong_hits >= 1
        or (weak_hits >= 2 and len(weak_parts) >= 2)
    )

    # Support signals
    has_bio_kw  = any(kw in snippet_lower for kw in BIO_KEYWORDS)
    has_company = bool(company) and company.lower() in snippet_lower

    # Company domain in URL
    company_words  = [w for w in company.lower().split() if len(w) > 3] if company else []
    company_in_url = sum(1 for w in company_words if w in url_lower) >= 2

    strong_signals  = sum([name_in_url, name_in_start, full_name_match])
    support_signals = sum([has_bio_kw, has_company])

    # Empty snippet — rely on URL only
    if len(snippet.strip()) < 50:
        if name_in_url:
            return True,  "medium", "[heuristic] empty snippet, name matched in URL"
        if company_in_url and company:
            return True,  "low",    "[heuristic] empty snippet, company domain matched in URL"
        return False, "low", "[heuristic] empty snippet, no URL signals"

    if full_name_match and support_signals >= 1:
        is_valid, confidence = True,  "high"
    elif strong_signals >= 1:
        is_valid, confidence = True,  "high" if support_signals >= 1 else "medium"
    elif name_in_snippet and support_signals >= 2:
        is_valid, confidence = True,  "medium"
    elif company_in_url and support_signals >= 2:
        is_valid, confidence = True,  "medium"
    else:
        is_valid, confidence = False, "low"

    parts = []
    if full_name_match:  parts.append("full name match")
    if name_in_url:      parts.append(f"name in URL ({url_part_hits} parts)")
    if name_in_start:    parts.append(f"name in snippet start ({early_part_hits} parts)")
    if strong_hits:      parts.append(f"strong parts in snippet ({strong_hits})")
    if weak_hits:        parts.append(f"weak parts in snippet ({weak_hits})")
    if has_bio_kw:       parts.append("bio keywords")
    if has_company:      parts.append("company in snippet")
    if company_in_url:   parts.append("company in URL")
    if not parts:        parts.append(
        f"no signals (url:{url_part_hits} strong:{strong_hits} weak:{weak_hits})"
    )

    return is_valid, confidence, "[heuristic] " + ", ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# LLM VALIDATION
# ─────────────────────────────────────────────────────────────────────────────
def _build_validation_prompt(name: str, company: str, url: str, snippet: str) -> str:
    company_line = f"Company: {company}\n" if company else ""
    name_parts = name.strip().split()
    short_form  = " ".join(name_parts[:2]) if len(name_parts) > 2 else None
    disambiguation = f"""
CRITICAL DISAMBIGUATION RULE:
- Do NOT infer or guess that a different person "could be" or "might be" {name}.
- When in doubt, return false. Only return true if you are certain.
The full name is "{name}". This person may also appear as "{short_form}" in some sources.
- If the snippet only mentions "{short_form}" (without further context linking to THIS specific individual), return false.
- Only return true if the snippet mentions the FULL name "{name}", OR clearly identifies this specific person via role/company/other unique details that match known facts about them.
- Do NOT assume "{short_form}" = "{name}" without corroborating evidence in the snippet itself.
""" if short_form and short_form.lower() != name.lower() else ""
    return f"""Does this snippet contain information about {name}?
{company_line}{disambiguation}URL: {url}
Snippet: {snippet[:200]}

Return JSON only: {{"is_valid": true, "confidence": "high", "reason": "..."}}"""


def _parse_validation_response(raw: str):
    if not raw or not raw.strip():
        return False, "low", "empty LLM response"

    cleaned = re.sub(r"```json|```", "", raw).strip()

    KEY_ALIASES = {
        "is_valid":   ["is_valid", "isvalid", "valid", "is_relevant", "relevant", "match"],
        "confidence": ["confidence", "conf", "certainty", "level", "score"],
        "reason":     ["reason", "explanation", "rationale", "justification", "note", "details"],
    }

    def _normalise_keys(d: dict) -> dict:
        normalised = {}
        for canon, aliases in KEY_ALIASES.items():
            for alias in aliases:
                for k, v in d.items():
                    if k.lower().replace("-", "_") == alias:
                        normalised[canon] = v
                        break
                if canon in normalised:
                    break
        return normalised

    def _try_parse_json(text: str):
        try:
            return json.loads(text)
        except Exception:
            pass
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        for m in re.finditer(r'\{[^{}]+\}', text, re.DOTALL):
            try:
                return json.loads(m.group())
            except Exception:
                continue
        return None

    parsed = _try_parse_json(cleaned)
    if parsed and isinstance(parsed, dict):
        if len(parsed) == 1:
            inner = list(parsed.values())[0]
            if isinstance(inner, dict):
                parsed = inner
        normalised = _normalise_keys(parsed)
        if "is_valid" in normalised:
            raw_val    = normalised["is_valid"]
            is_valid   = raw_val.lower().strip() in ("true", "yes", "1") if isinstance(raw_val, str) else bool(raw_val)
            confidence = str(normalised.get("confidence", "medium")).lower()
            if confidence not in ("high", "medium", "low"):
                confidence = "medium"
            reason = str(normalised.get("reason", "parsed ok"))
            return is_valid, confidence, reason

    lower = cleaned.lower()
    pos_patterns = [
        r'"is_valid"\s*:\s*true', r'"valid"\s*:\s*true',
        r'\bthis (is|does) (refer|relate|mention|describe)',
        r'\bsnippet (is|does) (about|refer|contain)',
        r'\bclearly (refers?|is) (to|about)', r'\brelevant\b',
    ]
    neg_patterns = [
        r'"is_valid"\s*:\s*false', r'"valid"\s*:\s*false',
        r'\bnot (about|related|relevant|referring)\b',
        r'\bdifferent (person|individual)\b',
        r'\bdoes not (mention|refer|contain|relate)\b',
        r'\bno (mention|reference|information)\b',
        r'\bunrelated\b', r'\bcannot (confirm|verify)\b',
    ]
    pos_hits = sum(1 for p in pos_patterns if re.search(p, lower))
    neg_hits = sum(1 for p in neg_patterns if re.search(p, lower))
    if pos_hits > neg_hits and pos_hits >= 1:
        return True,  "low", f"natural language fallback: {pos_hits} pos, {neg_hits} neg"
    if neg_hits > pos_hits and neg_hits >= 1:
        return False, "low", f"natural language fallback: {neg_hits} neg, {pos_hits} pos"

    return False, "low", "could not parse LLM response"


# ─────────────────────────────────────────────────────────────────────────────
# RECONCILIATION — combine LLM + heuristic verdicts
# ─────────────────────────────────────────────────────────────────────────────
CONF_RANK = {"high": 3, "medium": 2, "low": 1}

def _reconcile(
    llm_valid: bool,       llm_conf: str,       llm_reason: str,       llm_failed: bool,
    heur_valid: bool,      heur_conf: str,       heur_reason: str,
) -> tuple:
    """
    Combine LLM and heuristic results into a single verdict.

    Rules (in priority order):
    1. LLM failed (timeout/empty/parse) → trust heuristic entirely
    2. Both agree                        → trust the higher-confidence one
    3. Disagree, LLM high-confidence     → trust LLM (override heuristic)
    4. Disagree, heuristic high-conf     → trust heuristic (LLM may have hallucinated)
    5. Disagree, both medium/low         → conservative: reject, flag for review
    """
    if llm_failed:
        return heur_valid, heur_conf, f"[llm-failed] {heur_reason}", "heuristic"

    # Both agree
    if llm_valid == heur_valid:
        # Pick the higher-confidence result for the reason string
        if CONF_RANK.get(llm_conf, 0) >= CONF_RANK.get(heur_conf, 0):
            return llm_valid, llm_conf, f"[agree] llm: {llm_reason}", "llm+heuristic"
        else:
            return heur_valid, heur_conf, f"[agree] heuristic: {heur_reason}", "llm+heuristic"

    if not llm_valid and not heur_valid:
        # Both reject — pick higher-confidence reason
        if CONF_RANK.get(llm_conf, 0) >= CONF_RANK.get(heur_conf, 0):
            return False, llm_conf,  f"[agree-reject] llm: {llm_reason}", "llm+heuristic"
        else:
            return False, heur_conf, f"[agree-reject] heuristic: {heur_reason}", "llm+heuristic"

    # Both medium/low and disagree → conservative reject
    return False, "low", f"[conflict] llm({llm_conf})={llm_valid}: {llm_reason} | heur({heur_conf})={heur_valid}: {heur_reason}", "llm+heuristic"

# ─────────────────────────────────────────────────────────────────────────────
# PER-URL VALIDATION — runs LLM + heuristic in parallel, then reconciles
# ─────────────────────────────────────────────────────────────────────────────
def _validate_url(url: str, snippet: str, name: str, company: str) -> dict:
    # Run LLM and heuristic concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        llm_future  = ex.submit(ask_llm_validate, _build_validation_prompt(name, company, url, snippet))
        heur_future = ex.submit(_heuristic_validate, url, snippet, name, company)

        raw                             = llm_future.result()
        heur_valid, heur_conf, heur_reason = heur_future.result()

    llm_valid, llm_conf, llm_reason = _parse_validation_response(raw)
    llm_failed = llm_reason in FALLBACK_REASONS

    is_valid, confidence, reason, method = _reconcile(
        llm_valid, llm_conf, llm_reason, llm_failed,
        heur_valid, heur_conf, heur_reason,
    )

    return {
        "_valid":      is_valid,
        "_confidence": confidence,
        "_val_reason": reason,
        "_val_method": method,
    }


# ─────────────────────────────────────────────────────────────────────────────
# BATCH VALIDATION ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────────
def run(results: list, name: str, company: str = "") -> tuple:
    """
    Validates all search results sequentially (one URL at a time to avoid
    overloading local Ollama), deduplicating by URL first.

    Input:  list[list[dict]] or list[dict] — each item has 'url', 'snippet', 'attribute'
    Returns: (valid_results, rejected_results)
    """
    if not results:
        return [], []

    # Flatten
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

    # Deduplicate by URL
    url_to_items  = {}
    url_to_sample = {}
    for item in flat_results:
        url = item.get("url", "")
        if url not in url_to_items:
            url_to_items[url]  = []
            url_to_sample[url] = item
        url_to_items[url].append(item)

    unique_urls = list(url_to_sample.keys())
    saved = len(flat_results) - len(unique_urls)
    print(f"\n  [Validation] {len(flat_results)} results -> {len(unique_urls)} unique URLs "
          f"({saved} duplicate URL validations skipped)")

    # Sequential — one LLM call at a time to avoid overloading Ollama
    # Heuristic runs in parallel with each LLM call inside _validate_url
    val_results = []
    for i, url in enumerate(unique_urls):
        snippet = url_to_sample[url].get("snippet", "")
        print(f"    [{i+1:02d}/{len(unique_urls):02d}] Validating: {url[:70]}")
        val = _validate_url(url, snippet, name, company)
        val_results.append((url, val))
        time.sleep(0.3)

    # Build cache
    url_cache = {url: val for url, val in val_results}

    # Re-attach to all original items
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

    printed_urls     = set()
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

    method_counts = {}
    for _, val in url_cache.items():
        m = val.get("_val_method", "unknown")
        method_counts[m] = method_counts.get(m, 0) + 1

    print(f"\n  Summary : {len(valid_results)} valid, {len(rejected_results)} rejected "
          f"(from {len(validated_flat)} total, {len(unique_urls)} unique URLs validated)")
    print(f"  Methods : " + ", ".join(f"{v} via {k}" for k, v in method_counts.items()))

    # Safety net
    if not valid_results and rejected_results:
        salvageable = [r for r in rejected_results if r["_confidence"] in ("high", "medium")]
        if salvageable:
            print(f"\n  WARNING: All results rejected -- salvaging {len(salvageable)} medium/high-confidence results")
            valid_results    = salvageable
            rejected_results = [r for r in rejected_results if r not in salvageable]

    print(f"{'='*75}")
    return valid_results, rejected_results