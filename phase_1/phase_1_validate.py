import re
import json
import concurrent.futures
from phase_1_utils import ask_llm, fmt_source


# BIO KEYWORDS FOR HEURISTIC CHECK

BIO_KEYWORDS = [
    "born", "ceo", "founder", "chairman", "director", "president",
    "education", "net worth", "nationality", "university", "college",
    "billion", "million", "age", "studied", "graduated", "degree",
    "career", "appointed", "executive", "managing", "entrepreneur",
]


# HEURISTIC VALIDATION (no LLM)

def _heuristic_validate(page: dict, name: str, company: str) -> tuple:
    """
    Pure Python validation using URL, title, name frequency, and bio keywords.
    Returns (is_valid, confidence, reason)

    Name matching uses individual name parts (not full string) so partial matches
    like 'daniel-teo' in URL correctly match 'Daniel Teo Tong How'.

    Signals:
      STRONG  -- name parts in URL (2+), name parts in page title (2+)
      MEDIUM  -- name parts in first 500 chars (2+), min part frequency >= 3
      SUPPORT -- bio keywords present, company name present
    Passes if: any STRONG signal OR (2+ MEDIUM signals AND 1 SUPPORT signal)
    """
    url        = page.get("url", "")
    text       = page.get("text", "")
    name_lower = name.lower()
    text_lower = text.lower()
    url_lower  = url.lower()

    # Split name into meaningful tokens (skip very short ones like 'de', 'al')
    name_parts = [p for p in name_lower.split() if len(p) > 2]

    # STRONG: name in URL
    # Check full slugified name OR at least 2 individual parts present in URL
    name_slug     = name_lower.replace(" ", "_")
    name_slug2    = name_lower.replace(" ", "-")
    url_part_hits = sum(1 for p in name_parts if p in url_lower)
    name_in_url   = name_slug in url_lower or name_slug2 in url_lower or url_part_hits >= 2

    # STRONG: name in page title (first line of text)
    first_line      = text[:200].split("\n")[0].lower()
    title_part_hits = sum(1 for p in name_parts if p in first_line)
    name_in_title   = name_lower in first_line or title_part_hits >= 2

    # MEDIUM: name parts in first 500 chars
    early_part_hits = sum(1 for p in name_parts if p in text_lower[:500])
    in_early        = name_lower in text_lower[:500] or early_part_hits >= 2

    # MEDIUM: frequency -- use the least-common part count to avoid
    # over-counting very common tokens like 'teo' appearing everywhere
    part_counts = [text_lower.count(p) for p in name_parts] if name_parts else [0]
    name_count  = min(part_counts)
    high_freq   = name_count >= 3

    # SUPPORT: bio keywords and company name
    has_bio_kw  = any(kw in text_lower for kw in BIO_KEYWORDS)
    has_company = bool(company) and company.lower() in text_lower

    # Decision logic
    strong_signals  = sum([name_in_url, name_in_title])
    medium_signals  = sum([in_early, high_freq])
    support_signals = sum([has_bio_kw, has_company])

    if strong_signals >= 1:
        is_valid   = True
        confidence = "high" if support_signals >= 1 else "medium"
    elif medium_signals >= 2 and support_signals >= 1:
        is_valid   = True
        confidence = "medium"
    elif medium_signals >= 1 and support_signals >= 2:
        is_valid   = True
        confidence = "medium"
    else:
        is_valid   = False
        confidence = "low"

    # Build reason string
    parts = []
    if name_in_url:   parts.append(f"name in URL ({url_part_hits} parts matched)")
    if name_in_title: parts.append(f"name in title ({title_part_hits} parts matched)")
    if in_early:      parts.append(f"name in opening ({early_part_hits} parts matched)")
    if high_freq:     parts.append(f"name appears {name_count}x (min part freq)")
    if has_bio_kw:    parts.append("bio keywords found")
    if has_company:   parts.append("company mentioned")
    if not parts:     parts.append(f"name parts matched {url_part_hits}x in URL, {early_part_hits}x in opening, min freq {name_count}")

    reason = "[heuristic] " + ", ".join(parts)
    return is_valid, confidence, reason


# VALIDATION PROMPT

def _build_validation_prompt(name: str, company: str, url: str, text: str) -> str:
    company_line = f"  - Known company/organisation: {company}" if company else ""
    return f"""You are checking whether a webpage is actually about a specific person.

Person we are researching:
  - Name: {name}{company_line}

Source URL: {url}

Page content (first 2000 chars):
{text[:2000]}

Your job is to decide: does this page contain real biographical or professional information
about THIS specific person — the one named above?

Rules:
- Return "yes" ONLY if the page clearly discusses the specific individual named above
  (e.g. their career, biography, net worth, education, business dealings, awards, interviews, etc.)
- Return "no" if:
    * The page is about a DIFFERENT person who happens to share the same name
    * The name appears only incidentally (e.g. in a list, passing mention, unrelated context)
    * The page is a generic directory, search results page, or placeholder with no real content
    * The page content is mostly irrelevant to the person (e.g. a company page where this
      person is only a footnote)
    * The page is clearly about a company/org but does NOT discuss this person personally
    * The page is about someone whose name partially overlaps but is clearly a different individual
- If the company is provided and the page discusses that company AND the person together,
  that is a strong signal to return "yes"
- If the name is common and the page gives no clear signals it's the right person, return "no"
- IMPORTANT: If a company/organisation is provided, the page must be about the person in THAT
  specific professional context. A page about a different person who happens to share the same
  name but works in a completely different field/industry must be rejected.
- Example: if researching "Jackie Chan" from "Winning International Group" (shipping company),
  a page about the Hong Kong actor Jackie Chan must be rejected even though the name matches.

You MUST respond with ONLY this exact JSON on a single line, nothing else — no preamble, no explanation, no markdown, no backticks:
{{"is_valid": true, "confidence": "high", "reason": "your reason here"}}"""

def _check_wrong_person(reason: str, name: str) -> bool:
    """
    Returns True if the reason string mentions a name that looks
    different from our target — signal that LLM accepted wrong person.
    """
    name_parts = set(name.lower().split())
    # Extract capitalised word pairs from reason (likely person names)
    words = reason.split()
    for i in range(len(words) - 1):
        pair = (words[i].strip(".,").lower(), words[i+1].strip(".,").lower())
        # If both words are not in our name parts, it's likely a different person
        if (len(pair[0]) > 2 and len(pair[1]) > 2 and
            pair[0] not in name_parts and pair[1] not in name_parts):
            return True
    return False
# JSON PARSING WITH FALLBACKS

def _parse_validation_response(raw: str):
    """
    Three-layer parsing:
      1. Direct JSON parse after stripping markdown fences
      2. Extract first {...} block via regex, then parse
      3. Keyword scan for true/false as last resort
    Returns (is_valid, confidence, reason)
    """
    # Layer 1 -- strip markdown fences and try direct parse
    cleaned = re.sub(r"```json|```", "", raw).strip()
    try:
        parsed     = json.loads(cleaned)
        is_valid   = bool(parsed.get("is_valid", False))
        confidence = parsed.get("confidence", "low")
        reason     = parsed.get("reason", "parsed ok")
        return is_valid, confidence, reason
    except Exception:
        pass

    # Layer 2 -- extract first {...} block and try again
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

    # Layer 3 -- keyword scan on raw text
    lower = raw.lower()
    if '"is_valid": true' in lower or '"is_valid":true' in lower:
        return True, "medium", "keyword fallback: is_valid true found in response"
    if '"is_valid": false' in lower or '"is_valid":false' in lower:
        return False, "medium", "keyword fallback: is_valid false found in response"

    # Total failure
    return False, "low", "could not parse LLM response"


# PER-PAGE VALIDATION

def validate_page(page: dict, name: str, company: str) -> dict:
    """
    Validation flow (heuristic first for speed):
      1. Run heuristic — if HIGH confidence, use result immediately (no LLM call)
      2. If heuristic is MEDIUM/LOW — call LLM to decide
      3. If LLM parse fails — use heuristic result as fallback

    This avoids LLM calls for clearly valid or clearly invalid pages,
    significantly reducing validation time.
    """
    url  = page["url"]

    # Step 1 — heuristic first
    is_valid, confidence, reason = _heuristic_validate(page, name, company)
    method = "heuristic"

    # Step 2 — only call LLM if heuristic is uncertain (medium/low confidence)
    if confidence in ("medium", "low"):
        prompt = _build_validation_prompt(name, company, url, page["text"])
        raw    = ask_llm(prompt)
        llm_valid, llm_confidence, llm_reason = _parse_validation_response(raw)

        if llm_reason != "could not parse LLM response":
            is_valid   = llm_valid
            confidence = llm_confidence
            reason     = llm_reason
            method     = "llm"
        # else keep heuristic result

    return {
        **page,
        "_valid":      is_valid,
        "_confidence": confidence,
        "_val_reason": reason,
        "_val_method": method,
    }


# BATCH VALIDATION

def validate_all(pages: list, name: str, company: str = "") -> list:
    """
    Runs validation in parallel across all pages.
    Returns two lists: (valid_pages, rejected_pages)
    Prints a summary table to stdout.
    """
    print(f"\n  [Validation] Checking {len(pages)} pages are actually about '{name}'...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(pages))) as executor:
        results = list(executor.map(
            lambda p: validate_page(p, name, company),
            pages
        ))

    print(f"\n{'='*65}")
    print(f"  VALIDATION RESULTS")
    print(f"{'='*65}")

    valid_pages    = []
    rejected_pages = []

    for r in results:
        src    = r.get("url", "")
        status = "✓ VALID   " if r["_valid"] else "✗ REJECTED"
        conf   = r["_confidence"].upper()
        reason = r["_val_reason"]
        method = r.get("_val_method", "llm").upper()
        print(f"  {status} [{conf:6s}] [{method:9s}] {src}")
        print(f"             -> {reason}")

        if r["_valid"]:
            valid_pages.append(r)
        else:
            rejected_pages.append(r)

    llm_count       = sum(1 for r in results if r.get("_val_method") == "llm")
    heuristic_count = sum(1 for r in results if r.get("_val_method") == "heuristic")
    print(f"\n  Summary : {len(valid_pages)} valid, {len(rejected_pages)} rejected "
          f"(from {len(results)} total)")
    print(f"  Methods : {llm_count} via LLM, {heuristic_count} via heuristic fallback")

    # Safety net -- if everything got rejected, salvage medium/high confidence ones
    if not valid_pages and rejected_pages:
        salvageable = [r for r in rejected_pages if r["_confidence"] in ("high", "medium")]
        if salvageable:
            print(f"\n  WARNING: All pages rejected -- salvaging {len(salvageable)} medium/high-confidence pages")
            valid_pages    = salvageable
            rejected_pages = [r for r in rejected_pages if r not in salvageable]

    print(f"{'='*65}")
    return valid_pages, rejected_pages