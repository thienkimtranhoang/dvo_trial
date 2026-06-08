"""
Phase 4 Merge — Organisation
LLM merging per attribute for organisation profiles.
"""
import re
import json
import time
import requests
import concurrent.futures
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import OLLAMA_URL, OLLAMA_MODEL

ORG_ATTRIBUTES = [
    "DATE_OF_ESTABLISHMENT",
    "BIOGRAPHY",
    "GIVING",
    "DEMONSTRATED_INTERESTS",
    "OTHER_INTERESTING_FACTS",
    "POTENTIAL_CONNECTORS",
    "ADVERSE_NEWS",
]


def ask_llm(prompt: str, num_predict: int = 3000) -> str:
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


def build_org_prompt(attr: str, name: str, sources_text: str, source_list: str) -> str:
    base = f"""You are writing the {attr} section about {name} for a professional profile document.

Sources:
{sources_text}

Source reference list:
{source_list}

General rules:
- Write a clear factual paragraph with precise details.
- Always include specific numbers, amounts, years and named organisations.
- Merge and deduplicate all facts — never repeat the same information.
- Add inline citation [[N]] after each fact — inline next to facts, NOT at the end.
- Only include information from the sources — do NOT invent anything.
- Return ONLY the paragraph text, no headers, no extra text.

"""

    if attr == "DATE_OF_ESTABLISHMENT":
        return base + f"""Write when {name} was founded or incorporated.
Use exact date/month/year or year only — whatever is available. Do NOT guess. One to two sentences maximum."""

    if attr == "BIOGRAPHY":
        return base + f"""Write a comprehensive narrative about {name}:
- Founding story and origin/inspiration — who founded it and why
- Core mission and what the organisation does
- All named properties, assets, funds, programmes — list them specifically
- Key milestones with dates
- Current scale: markets, cities, countries, assets under management
- Named executives with titles
- CSR pillars, strategic priorities or budget commitments
- Do NOT include donations (those go in GIVING)"""

    if attr == "POTENTIAL_CONNECTORS":
        return base + f"""List key named individuals and organisations connected to {name}:
- Founders, executives, board members with exact titles
- Strategic partners, joint venture partners, major investors
- Government bodies or institutions with formal relationships
- For each: full name, title, relationship to {name}
- Write as a flowing prose paragraph, NO bullet points, NO bold text, NO headers."""

    if attr == "ADVERSE_NEWS":
        return base + f"""Start directly with the first adverse fact — no meta-phrases.
Include ALL controversies, lawsuits, regulatory issues, criticism about {name}.
Be factual and neutral. Only write "No adverse news found." if sources have zero negative content."""

    return base


def merge_attribute(attr: str, chunks: list, name: str) -> dict:
    if not chunks:
        return {"attribute": attr, "content": None, "sources": []}

    sources = []
    seen    = set()
    for c in chunks:
        url = c["source_url"]
        if url not in seen:
            seen.add(url)
            sources.append(url)

    sources_text = ""
    for i, c in enumerate(chunks, 1):
        src_num = sources.index(c["source_url"]) + 1
        # For GIVING use full 3000 chars to get all donation details
        max_len = 3000 if attr == "GIVING" else 1500
        text    = c["text"][:max_len] if len(c["text"]) > max_len else c["text"]
        sources_text += f"\nSource [{src_num}] ({c['source_url']}):\n{text}\n"

    source_list = "\n".join(f"[{i+1}] {url}" for i, url in enumerate(sources))
    prompt      = build_org_prompt(attr, name, sources_text, source_list)
    # Use higher num_predict for GIVING to get full detailed output
    predict = 5000 if attr == "GIVING" else 4000
    content     = ask_llm(prompt, num_predict=predict)

    print(f"    ✅ {attr:<30} merged ({len(chunks)} sources)")
    return {"attribute": attr, "content": content, "sources": sources}


def merge_interests_and_facts(
    interests_chunks: list,
    facts_chunks: list,
    name: str
) -> tuple:
    """
    Merge DEMONSTRATED_INTERESTS and OTHER_INTERESTING_FACTS in one LLM call.
    LLM classifies each piece into exactly one section.
    If LLM finds giving content, it can also return GIVING.
    """
    # Combine chunks, deduplicate
    seen_urls  = set()
    all_chunks = []
    for c in interests_chunks + facts_chunks:
        key = (c["source_url"], c["text"][:50])
        if key not in seen_urls:
            seen_urls.add(key)
            all_chunks.append(c)

    empty = {"content": None, "sources": []}
    if not all_chunks:
        return (
            {**empty, "attribute": "GIVING"},
            {**empty, "attribute": "DEMONSTRATED_INTERESTS"},
            {**empty, "attribute": "OTHER_INTERESTING_FACTS"},
        )

    sources = []
    seen    = set()
    for c in all_chunks:
        url = c["source_url"]
        if url not in seen:
            seen.add(url)
            sources.append(url)

    sources_text = ""
    for i, c in enumerate(all_chunks, 1):
        src_num = sources.index(c["source_url"]) + 1
        text    = c["text"][:2000] if len(c["text"]) > 2000 else c["text"]
        sources_text += f"\nSource [{src_num}] ({c['source_url']}):\n{text}\n"

    source_list = "\n".join(f"[{i+1}] {url}" for i, url in enumerate(sources))

    prompt = f"""You are classifying content about the organisation {name} into three sections for a professional profile.

Sources:
{sources_text}

Source reference list:
{source_list}

Classify ALL content into EXACTLY ONE of these three sections:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GIVING — ALL concrete financial giving and donations by {name}:
  - ANY donation of money or resources to an external organisation goes HERE — not in DEMONSTRATED_INTERESTS
  - Specific donations with exact year and amount (S$, US$ etc) to named recipient organisations
  - Example: "Mapletree donated S$250,000 to Singapore International Foundation" → GIVING
  - Example: "Mapletree gave S$66,000 to fund the Mapletree-TENG Scholarship" → GIVING
  - Named scholarships, bursaries, awards funded with amounts
  - In-kind donations with quantities (e.g. "2 million medical masks")
  - Infrastructure or community projects funded with specifics
  - Group under categories: Education / Arts / Healthcare / Environment / Community
  - Do NOT include NUS-related giving
  - If an amount OR a named recipient organisation is mentioned, include it — do not skip
  - Even if the exact amount is not clear, include it if it is clearly a donation or grant

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEMONSTRATED_INTERESTS — what {name} actively champions and stands for as an organisation:
  - Strategic causes and values publicly committed to (e.g. sustainability, green energy)
  - Membership in global frameworks (e.g. UN PRI signatory, GRI reporting, SDG alignment)
  - Named recurring annual programmes or events the organisation runs
  - Community engagement plans and long-term commitments
  - Things the organisation DOES regularly or BELIEVES IN — not one-off donations
  - The four CSR pillars if mentioned (arts, education, environment, healthcare)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OTHER_INTERESTING_FACTS — unique notable facts about {name} not covered above:
  - Specific acquisitions or deals with exact values and locations
  - Records, firsts, rankings, scale milestones (e.g. "managed S$80.3 billion AUM as of March 2025")
  - Awards received with year and awarding body
  - Named developments or projects with completion dates
  - Market expansion milestones with specific year and geography
  - Any highly specific surprising or notable fact

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STRICT RULES:
- Every piece of content goes in EXACTLY ONE section — never duplicated
- Add inline citation [[N]] after each fact
- Write each section as a well-structured detailed paragraph
- If a section has no content, return null for it
- Do NOT invent anything not in the sources

Return ONLY valid JSON:
{{"GIVING": "paragraph or null", "DEMONSTRATED_INTERESTS": "paragraph or null", "OTHER_INTERESTING_FACTS": "paragraph or null"}}"""

    raw = ask_llm(prompt, num_predict=5000)
    raw = re.sub(r"```json|```", "", raw).strip()
    # Fix common LLM JSON issues
    raw = re.sub(r",\s*}", "}", raw)   # trailing comma before }
    raw = re.sub(r",\s*]", "]", raw)   # trailing comma before ]
    raw = re.sub(r"[--]", "", raw)  # control chars

    try:
        parsed            = json.loads(raw)
        giving_content    = parsed.get("GIVING")
        interests_content = parsed.get("DEMONSTRATED_INTERESTS")
        facts_content     = parsed.get("OTHER_INTERESTING_FACTS")
        print(f"    ✅ DEMONSTRATED_INTERESTS + OTHER_INTERESTING_FACTS merged ({len(all_chunks)} sources)")
    except Exception as e:
        print(f"    ⚠️  Combined interests/facts merge failed: {e} — using fallback")
        # Fallback: run separately
        giving_content    = None
        interests_content = None
        facts_content     = None

    return (
        giving_content,
        {"attribute": "DEMONSTRATED_INTERESTS", "content": interests_content, "sources": sources},
        {"attribute": "OTHER_INTERESTING_FACTS","content": facts_content,     "sources": sources},
    )



def cross_deduplicate_org(results: dict, name: str) -> dict:
    """Remove duplicates across GIVING, DEMONSTRATED_INTERESTS, OTHER_INTERESTING_FACTS."""
    giving    = results.get("GIVING", {}).get("content", "") or ""
    interests = results.get("DEMONSTRATED_INTERESTS", {}).get("content", "") or ""
    facts     = results.get("OTHER_INTERESTING_FACTS", {}).get("content", "") or ""

    if not any([giving, interests, facts]):
        return results

    # Clean each section individually — ask LLM to remove content from other sections
    def clean_section(section_name, section_text, other_sections):
        if not section_text:
            return section_text
        others_text = ""
        for name_s, text_s in other_sections.items():
            if text_s:
                others_text += f"{name_s}:\n{text_s[:400]}\n\n"
        prompt = (
            f"You are cleaning the {section_name} section of a profile.\n"
            f"Remove sentences that repeat content already in other sections.\n\n"
            f"OTHER SECTIONS COVER:\n{others_text}"
            f"TEXT TO CLEAN:\n{section_text}\n\n"
            "Instructions:\n"
            "- Remove only sentences that duplicate content in other sections.\n"
            "- Keep all [[N]] citations intact.\n"
            "- Return ONLY the cleaned paragraph text — no labels, no headers, no section names.\n"
            "- Start directly with the content."
        )
        cleaned = ask_llm(prompt, num_predict=2000)
        return cleaned if cleaned and len(cleaned) > 30 else section_text

    # Clean OTHER_INTERESTING_FACTS (most likely to have duplicates)
    cleaned_facts = clean_section(
        "OTHER_INTERESTING_FACTS",
        facts,
        {"GIVING": giving, "DEMONSTRATED_INTERESTS": interests}
    )

    # Clean DEMONSTRATED_INTERESTS
    cleaned_interests = clean_section(
        "DEMONSTRATED_INTERESTS",
        interests,
        {"GIVING": giving, "OTHER_INTERESTING_FACTS": cleaned_facts}
    )

    # Strip any prompt prefixes the LLM may have included
    def strip_prefix(text, prefix):
        if text and text.strip().startswith(prefix):
            text = text.strip()[len(prefix):].strip().lstrip(":").strip()
        return text

    cleaned_facts     = strip_prefix(cleaned_facts, "OTHER_INTERESTING_FACTS")
    cleaned_interests = strip_prefix(cleaned_interests, "DEMONSTRATED_INTERESTS")
    cleaned_interests = strip_prefix(cleaned_interests, "CURRENT DEMONSTRATED_INTERESTS")

    # Only use cleaned version if it's substantial enough
    if cleaned_facts and len(cleaned_facts) > 100:
        results["OTHER_INTERESTING_FACTS"]["content"] = cleaned_facts
    if cleaned_interests and len(cleaned_interests) > 100:
        results["DEMONSTRATED_INTERESTS"]["content"] = cleaned_interests
    print(f"    ✅ Cross-deduplication complete")
    return results


# ── MAIN ──────────────────────────────────────────────────────────────────────

def run(attribute_buckets: dict, name: str) -> dict:
    # Pop the three sections for combined merge
    giving_chunks    = attribute_buckets.pop("GIVING", []) + attribute_buckets.pop("DONATION_HISTORY", [])
    interests_chunks = attribute_buckets.pop("DEMONSTRATED_INTERESTS", [])
    facts_chunks     = attribute_buckets.pop("OTHER_INTERESTING_FACTS", [])

    remaining = {k: v for k, v in attribute_buckets.items() if v}
    # Add GIVING to parallel merge if it has chunks
    if giving_chunks:
        remaining["GIVING"] = giving_chunks

    print(f"\n  Running {len(remaining) + (1 if giving_chunks else 0) + (1 if interests_chunks else 0) + (1 if facts_chunks else 0)} parallel LLM merge calls...")

    results = {}

    # Pre-filter: remove volunteering/event descriptions from GIVING chunks
    # These belong in DEMONSTRATED_INTERESTS not GIVING
    GIVING_EXCLUDE = ["volunteer", "community month", "futsal", "sketchwall", "thrift", 
                      "employee", "tenant", "learning hour", "arts in the city"]
    
    def filter_giving_chunk(chunk):
        text_lower = chunk["text"].lower()
        # Remove sentences mentioning volunteer events from giving
        sentences = chunk["text"].split(". ")
        kept = [s for s in sentences if not any(kw in s.lower() for kw in GIVING_EXCLUDE)]
        filtered_text = ". ".join(kept).strip()
        if len(filtered_text) > 50:
            return {**chunk, "text": filtered_text}
        return None

    if "GIVING" in remaining:
        remaining["GIVING"] = [c for c in (filter_giving_chunk(c) for c in remaining["GIVING"]) if c]

    # Run all attributes including GIVING in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        futures = {
            executor.submit(merge_attribute, attr, chunks, name): attr
            for attr, chunks in remaining.items()
        }
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results[result["attribute"]] = result

    # Run DEMONSTRATED_INTERESTS and OTHER_INTERESTING_FACTS separately
    if interests_chunks:
        remaining["DEMONSTRATED_INTERESTS"] = interests_chunks
    # Pre-filter facts chunks — remove volunteer/community event descriptions
    FACTS_EXCLUDE = ["community month", "volunteer", "futsal", "sketchwall", 
                     "thrift", "arts in the city", "learning hour"]
    
    def filter_facts_chunk(chunk):
        sentences = chunk["text"].split(". ")
        kept = [s for s in sentences if not any(kw in s.lower() for kw in FACTS_EXCLUDE)]
        filtered_text = ". ".join(kept).strip()
        if len(filtered_text) > 50:
            return {**chunk, "text": filtered_text}
        return None

    if facts_chunks:
        facts_chunks_filtered = [c for c in (filter_facts_chunk(c) for c in facts_chunks) if c]
        remaining["OTHER_INTERESTING_FACTS"] = facts_chunks_filtered if facts_chunks_filtered else facts_chunks

    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        futures2 = {
            executor.submit(merge_attribute, attr, chunks, name): attr
            for attr, chunks in {"DEMONSTRATED_INTERESTS": interests_chunks, "OTHER_INTERESTING_FACTS": facts_chunks}.items()
            if chunks
        }
        for future in concurrent.futures.as_completed(futures2):
            result = future.result()
            results[result["attribute"]] = result

    # Fill missing
    for attr in ORG_ATTRIBUTES:
        if attr not in results:
            results[attr] = {"attribute": attr, "content": None, "sources": []}

    # Ensure no None values in results
    for attr in ORG_ATTRIBUTES:
        if attr not in results or results[attr] is None:
            results[attr] = {"attribute": attr, "content": None, "sources": []}

    # Post-merge deduplication pass
    results = cross_deduplicate_org(results, name)

    return results
