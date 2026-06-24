import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
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
USE_IDENTITY_ANCHORS = True

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
    source_text = (snippet or "").strip()

    return f"""Validate whether this search result is about the target person.

Target person: {name}
Known company/context: {company or "none provided"}
URL: {url}
Snippet: {source_text[:700]}

Decide identity only. Ignore whether the topic would be useful for any downstream profile section.

Use semantic identity, not only exact string matching:
- Accept exact names or supported name variants/aliases when nearby context identifies the same person.
- Reject isolated partial-name matches.
- Reject same-name/different-person cases when role, organisation, topic, geography, or life details point elsewhere.
- Do not claim evidence that is not in the URL/snippet.

Check three things:
- Name evidence: full name, reversed name, initials, or a credible alias.
- Context evidence: company, role/title, biography details, dates, locations, or source domain.
- Conflict evidence: different employer/title, unrelated topic, or another person with the same/similar name.

Confidence guide:
- high: clear name + context evidence, with no meaningful conflict.
- medium: likely same person, but evidence is partial.
- low: weak, ambiguous, passing mention, or conflicting evidence.

If the snippet is only a directory/search/listing result, return true only when it clearly identifies the target person.

Return JSON only:
{{"is_valid": true, "confidence": "high", "reason": "...", "identity_evidence": "...", "negative_evidence": null}}"""



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
def _norm_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _name_parts(name: str) -> list[str]:
    return [p for p in _norm_text(name).split() if len(p) > 2]


def _name_signal(url: str, snippet: str, name: str) -> dict:
    text = _norm_text(f"{url} {snippet}")
    parts = _name_parts(name)
    if not parts:
        return {"strong": False, "partial": False, "hits": []}

    full_name = " ".join(parts)
    reversed_name = " ".join(reversed(parts))
    hits = [p for p in parts if re.search(rf"\b{re.escape(p)}\b", text)]
    strong = (
        bool(full_name and full_name in text)
        or bool(reversed_name and reversed_name in text)
        or len(hits) >= min(len(parts), 3)
    )
    partial = len(hits) >= min(len(parts), 2)
    return {"strong": strong, "partial": partial, "hits": hits}


def _parse_json_dict(raw: str) -> dict:
    if not raw or not raw.strip():
        return {}
    cleaned = re.sub(r"```json|```", "", raw).strip()
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            pass
    return {}


def _build_anchor_extraction_prompt(name: str, company: str, seed_sources: list[dict]) -> str:
    source_blocks = []
    for i, src in enumerate(seed_sources, 1):
        source_blocks.append(
            f"SOURCE {i}\nURL: {src['url']}\nSNIPPET: {src['snippet'][:700]}"
        )

    return f"""Extract a generic identity profile for the target person from trusted seed sources.

Target person: {name}
Known company/context: {company or "none provided"}

Seed sources:
{chr(10).join(source_blocks)}

Extract only source-supported identity anchors that can disambiguate this person from same-name people.
Prefer specific organisations, companies, foundations, named institutions, roles with organisations,
industries/domains, geography, family/company relationships, and name variants.
Also include distinctive identity descriptors that help disambiguation, such as source-supported
industry descriptors, property/business labels, philanthropic/art foundations, and named personal
projects. Do not include generic titles by themselves unless tied to a specific organisation or
clearly distinctive source context.

Return JSON only:
{{
  "name_variants": [],
  "organisations": [],
  "companies": [],
  "foundations": [],
  "roles_titles": [],
  "industries_domains": [],
  "locations": [],
  "family_or_relationships": [],
  "other_identity_anchors": []
}}"""


def _extract_anchor_profile(name: str, company: str, seed_sources: list[dict]) -> dict:
    if not seed_sources:
        return {}
    raw = ask_llm(_build_anchor_extraction_prompt(name, company, seed_sources))
    profile = _parse_json_dict(raw)
    if not profile:
        return {}
    return {
        key: value
        for key, value in profile.items()
        if isinstance(value, list) and value
    }


def _build_identity_profile(
    val_results: list[tuple[str, dict]],
    url_to_sample: dict,
    name: str,
    company: str,
    max_seed_sources: int = 3,
) -> dict:
    seed_urls = []
    seed_sources = []

    for url, val in val_results:
        if len(seed_urls) >= max_seed_sources:
            break
        if not val.get("_valid") or val.get("_confidence") == "low":
            continue

        snippet = url_to_sample[url].get("snippet", "")
        signal = _name_signal(url, snippet, name)
        if not signal["strong"]:
            continue

        seed_urls.append(url)
        seed_sources.append({"url": url, "snippet": snippet})

    anchors = _extract_anchor_profile(name, company, seed_sources)
    return {"anchors": anchors, "seed_urls": seed_urls, "seed_sources": seed_sources}


def _build_anchor_arbitration_prompt(
    name: str,
    company: str,
    profile: dict,
    url: str,
    snippet: str,
    current_reason: str,
) -> str:
    seed_blocks = []
    for i, src in enumerate(profile.get("seed_sources", []), 1):
        seed_blocks.append(
            f"SEED {i}\nURL: {src.get('url', '')}\nSNIPPET: {src.get('snippet', '')[:700]}"
        )

    return f"""Resolve whether a candidate search result is about the same target person.

Target person: {name}
Known company/context: {company or "none provided"}

Identity anchors extracted from stronger seed sources:
{json.dumps(profile.get("anchors", {}), ensure_ascii=False, indent=2)}

Trusted seed evidence excerpts:
{chr(10).join(seed_blocks)}

Candidate URL: {url}
Candidate snippet: {(snippet or "")[:900]}
Current validation reason: {current_reason}

Use the anchors semantically. For partial-name candidates, accept only if the candidate matches
specific anchor evidence such as organisation, company, foundation, role+organisation, industry,
location, relationship, or a clearly equivalent identity detail. Reject same-name/different-person
cases even if the topic seems profile-relevant.

If an exact anchor value appears in the candidate URL/snippet, put that exact value in matched_anchors.
If the candidate is valid by semantic identity evidence but does not use the exact anchor wording,
use evidence_bridge with:
- supporting_anchor: exact anchor value from the identity profile that the seed evidence supports
- candidate_evidence: exact short phrase copied from the candidate URL/snippet
- seed_evidence: exact short phrase copied from the trusted seed excerpts
- evidence_type: organisation, role, industry, location, relationship, project, foundation, or other

Do not use the target name alone as evidence. Do not return category names like "organisations",
"companies", "name", or "roles_titles" as matched anchors.

Return JSON only:
{{"is_valid": true, "confidence": "high", "matched_anchors": [], "evidence_bridge": {{"supporting_anchor": "", "candidate_evidence": "", "seed_evidence": "", "evidence_type": ""}}, "reason": "..."}}"""


def _anchor_arbitration_decision(
    name: str,
    company: str,
    profile: dict,
    url: str,
    snippet: str,
    current_reason: str,
) -> tuple:
    t0 = time.time()
    raw = ask_llm_validate(
        _build_anchor_arbitration_prompt(name, company, profile, url, snippet, current_reason)
    )
    elapsed = time.time() - t0
    print(f"    [Anchor Arbitration] {elapsed:.1f}s for {url[:70]}")
    parsed = _parse_json_dict(raw)
    if not parsed:
        return None, "low", "could not parse anchor arbitration response", [], {}

    raw_val = parsed.get("is_valid", parsed.get("valid", False))
    is_valid = raw_val.lower().strip() in ("true", "yes", "1") if isinstance(raw_val, str) else bool(raw_val)
    confidence = str(parsed.get("confidence", "medium")).lower()
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"
    reason = str(parsed.get("reason", "anchor arbitration parsed ok"))
    matched = parsed.get("matched_anchors", [])
    if not isinstance(matched, list):
        matched = [str(matched)] if matched else []
    evidence_bridge = parsed.get("evidence_bridge", {})
    if not isinstance(evidence_bridge, dict):
        evidence_bridge = {}
    return is_valid, confidence, reason, matched, evidence_bridge


def _flatten_anchor_values(anchors: dict) -> list[tuple[str, str]]:
    values = []

    def collect(item, category=""):
        if isinstance(item, str):
            if item.strip():
                values.append((category, item.strip()))
        elif isinstance(item, list):
            for sub_item in item:
                collect(sub_item, category)
        elif isinstance(item, dict):
            for key, sub_item in item.items():
                collect(sub_item, str(key))

    collect(anchors)
    return values


def _anchor_lookup(profile: dict) -> dict:
    lookup = {}
    for category, value in _flatten_anchor_values(profile.get("anchors", {})):
        normalised = _norm_text(value)
        if normalised:
            lookup[normalised] = {"category": category, "value": value}
    return lookup


def _verified_anchor_matches(profile: dict, matched: list, url: str, snippet: str) -> list[str]:
    anchors = profile.get("anchors", {})
    category_names = {_norm_text(k) for k in anchors.keys()}
    candidate_text = _norm_text(f"{url} {snippet}")
    anchor_map = _anchor_lookup(profile)

    verified = []

    def add_match(normalised: str):
        if not normalised or normalised in category_names:
            return
        if normalised in anchor_map and normalised in candidate_text:
            value = anchor_map[normalised]["value"]
            if value not in verified:
                verified.append(value)

    for item in matched:
        add_match(_norm_text(str(item)))

    # Do not rely only on the LLM copying matched_anchors correctly; scan directly too.
    for normalised in anchor_map:
        add_match(normalised)

    return verified


EVIDENCE_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "about", "his",
    "her", "their", "they", "them", "who", "has", "had", "was", "were", "are",
    "also", "will", "would", "could", "should", "mr", "mrs", "ms", "dr",
}


def _collect_strings(value) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        strings = []
        for item in value:
            strings.extend(_collect_strings(item))
        return strings
    if isinstance(value, dict):
        strings = []
        for item in value.values():
            strings.extend(_collect_strings(item))
        return strings
    return []


def _quote_supported(quote: str, text: str) -> bool:
    quote_norm = _norm_text(quote)
    text_norm = _norm_text(text)
    if not quote_norm or not text_norm:
        return False
    if quote_norm in text_norm:
        return True

    tokens = [t for t in quote_norm.split() if len(t) > 2]
    if len(tokens) < 4:
        return False
    hits = sum(1 for token in tokens if re.search(rf"\b{re.escape(token)}\b", text_norm))
    return hits / len(tokens) >= 0.8


def _has_non_name_signal(text: str, name: str) -> bool:
    name_tokens = set(_name_parts(name))
    tokens = [
        token
        for token in _norm_text(text).split()
        if len(token) > 2 and token not in name_tokens and token not in EVIDENCE_STOPWORDS
    ]
    return len(tokens) >= 2 or any(len(token) > 6 for token in tokens)


def _verified_evidence_bridge(
    profile: dict,
    evidence_bridge: dict,
    url: str,
    snippet: str,
    name: str,
) -> tuple[bool, str]:
    supporting_anchor = str(evidence_bridge.get("supporting_anchor", "")).strip()
    if not supporting_anchor:
        return False, ""

    anchor = _anchor_lookup(profile).get(_norm_text(supporting_anchor))
    if not anchor or anchor["category"] == "name_variants":
        return False, ""

    candidate_text = f"{url} {snippet}"
    seed_text = " ".join(
        f"{src.get('url', '')} {src.get('snippet', '')}"
        for src in profile.get("seed_sources", [])
    )

    candidate_quotes = _collect_strings(evidence_bridge.get("candidate_evidence"))
    seed_quotes = _collect_strings(evidence_bridge.get("seed_evidence"))
    candidate_ok = any(
        _quote_supported(quote, candidate_text) and _has_non_name_signal(quote, name)
        for quote in candidate_quotes
    )
    seed_ok = any(
        _quote_supported(quote, seed_text) and _has_non_name_signal(quote, name)
        for quote in seed_quotes
    )
    anchor_supported_by_seed = any(
        _quote_supported(supporting_anchor, quote) or _quote_supported(supporting_anchor, seed_text)
        for quote in seed_quotes
    )

    evidence_type = str(evidence_bridge.get("evidence_type", "")).lower().strip()
    weak_types = {"", "none", "name", "name_only", "same_name"}
    if candidate_ok and seed_ok and anchor_supported_by_seed and evidence_type not in weak_types:
        return True, supporting_anchor
    return False, ""


def _has_vote_conflict(val: dict) -> bool:
    llm_valid = val.get("_llm_valid")
    heur_valid = val.get("_heur_valid")
    if llm_valid is not None and heur_valid is not None:
        return llm_valid != heur_valid
    return str(val.get("_val_reason", "")).lstrip().startswith("[conflict]")


def _apply_identity_anchor_gate(
    url: str,
    val: dict,
    url_to_sample: dict,
    name: str,
    company: str,
    profile: dict,
) -> dict:
    if not profile.get("seed_urls") or not profile.get("anchors"):
        return val

    if not _has_vote_conflict(val):
        return val

    snippet = url_to_sample[url].get("snippet", "")
    anchor_valid, anchor_conf, anchor_reason, matched, evidence_bridge = _anchor_arbitration_decision(
        name,
        company,
        profile,
        url,
        snippet,
        val.get("_val_reason", ""),
    )

    if anchor_valid is None:
        gated = dict(val)
        gated["_valid"] = False
        gated["_confidence"] = "low"
        gated["_val_reason"] = (
            "[anchor-review] conflicting LLM/heuristic result needed anchor arbitration, "
            "but arbitration failed to parse"
        )
        gated["_val_method"] = f"{val.get('_val_method', 'validation')}+anchors"
        return gated

    verified_matches = _verified_anchor_matches(profile, matched, url, snippet)
    bridge_valid, bridge_anchor = _verified_evidence_bridge(
        profile,
        evidence_bridge,
        url,
        snippet,
        name,
    )
    if anchor_valid and not verified_matches and not bridge_valid:
        anchor_valid = False
        anchor_conf = "low"
        anchor_reason = (
            "Anchor arbitration accepted the source, but returned no concrete "
            "matched anchor values or verifiable seed/candidate evidence bridge"
        )

    gated = dict(val)
    gated["_valid"] = anchor_valid
    gated["_confidence"] = anchor_conf
    if anchor_valid and verified_matches:
        anchor_tag = "anchor-pass"
        matched_text = f" matched={verified_matches[:3]}"
    elif anchor_valid and bridge_valid:
        anchor_tag = "anchor-pass-evidence"
        matched_text = f" evidence_anchor={bridge_anchor}"
    else:
        anchor_tag = "anchor-reject"
        matched_text = f" matched={verified_matches[:3]}" if verified_matches else ""
    gated["_val_reason"] = f"[{anchor_tag}] {anchor_reason}{matched_text}"
    gated["_val_method"] = f"{val.get('_val_method', 'validation')}+anchors"
    return gated


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
        "_llm_valid":  llm_valid,
        "_llm_conf":   llm_conf,
        "_heur_valid": heur_valid,
        "_heur_conf":  heur_conf,
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
    t_validate = time.time()
    val_results = []
    for i, url in enumerate(unique_urls):
        snippet = url_to_sample[url].get("snippet", "")
        print(f"    [{i+1:02d}/{len(unique_urls):02d}] Validating: {url[:70]}")
        val = _validate_url(url, snippet, name, company)
        val_results.append((url, val))
        time.sleep(0.3)
    print(f"  [Timer] Validation only: {time.time() - t_validate:.1f}s")

    if USE_IDENTITY_ANCHORS:
        conflict_count = sum(1 for _, val in val_results if _has_vote_conflict(val))
        if conflict_count:
            t_anchor = time.time()
            identity_profile = _build_identity_profile(val_results, url_to_sample, name, company)
            print(f"  [Timer] Anchor profile extraction: {time.time() - t_anchor:.1f}s")
            if identity_profile["seed_urls"]:
                anchor_count = sum(len(v) for v in identity_profile.get("anchors", {}).values())
                print(
                    f"  [Identity Anchors] {len(identity_profile['seed_urls'])} seed sources, "
                    f"{anchor_count} semantic anchors for {conflict_count} conflict URLs"
                )
                for category, values in identity_profile.get("anchors", {}).items():
                    if values:
                        print(f"    - {category}: {', '.join(str(v) for v in values)}")
                t_anchor_gate = time.time()
                val_results = [
                    (
                        url,
                        _apply_identity_anchor_gate(url, val, url_to_sample, name, company, identity_profile),
                    )
                    for url, val in val_results
                ]
                print(f"  [Timer] Anchor arbitration/gating: {time.time() - t_anchor_gate:.1f}s")
                print(f"  [Timer] Identity anchors total: {time.time() - t_anchor:.1f}s")
            else:
                print("  [Identity Anchors] No strong seed sources found; skipping anchor gate")
        else:
            print("  [Identity Anchors] No LLM/heuristic conflicts found; skipping anchor gate")
    else:
        print("  [Identity Anchors] Disabled (set USE_IDENTITY_ANCHORS = True to enable)")

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
