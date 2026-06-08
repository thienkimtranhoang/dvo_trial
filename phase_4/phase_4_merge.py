import re
import json
import time
import requests
import concurrent.futures
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import OLLAMA_URL, OLLAMA_MODEL, ATTRIBUTES


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


# ── PER-ATTRIBUTE PROMPTS ─────────────────────────────────────────────────────

def build_prompt(attr: str, name: str, sources_text: str, source_list: str) -> str:

    base = f"""You are writing the {attr} section about {name} for a professional profile document.

Sources:
{sources_text}

Source reference list:
{source_list}

General rules:
- Write a single cohesive paragraph (NOT bullet points).
- Merge and deduplicate all facts — never repeat the same information.
- Add inline citation [[N]] after each fact referring to the source number.
- Only include information explicitly about {name}.
- Do NOT invent or infer anything not in the sources.
- Return ONLY the paragraph text with inline citations, no headers, no extra text.

"""

    if attr == "BIOGRAPHY":
        return base + f"""Specific rules for BIOGRAPHY:
- Cover {name}'s early life, career journey, major milestones and achievements.
- IMPORTANT: You MUST explicitly include these 4 fields if found in ANY source:
  * Age or date of birth (e.g. "born in 1964" or "aged 63")
  * Nationality or country of origin (e.g. "Chinese national" or "born in Shandong, China")
  * Education — school, university, degree (e.g. "graduated from Jiangsu Maritime Institute")
  * Personal net worth — include the exact dollar figure if mentioned in any source
  These will be extracted from the biography later so they MUST be present.
- DO NOT include: family members, hobbies, donations, philanthropic work, or interesting personal facts.
- Focus on professional and life story narrative.
- IMPORTANT: Place citations [[N]] inline next to the relevant facts, NOT all bunched together at the end.
- Do NOT put a long list of citations at the end of the paragraph.
"""

    if attr == "FAMILY":
        return base + f"""Specific rules for FAMILY:
- Write ONLY about {name}'s immediate family members: spouse, children, parents, siblings.
- ONLY include facts explicitly stated in the sources — no inference, no speculation.
- DO NOT mention birth place, nationality, lifestyle, personality traits, or career — those go elsewhere.
- DO NOT mention the source in the text.
- DO NOT include statements like "avoids lavish banquets" or "modest lifestyle" — only family relationships.
- If no family member information is found in sources, return exactly: "No family information is available in the public domain."
- Do NOT write a paragraph speculating about family if names/details are not in sources.
"""

    if attr == "INTERESTING_FACTS":
        return base + f"""Specific rules for INTERESTING_FACTS:
- Include ONLY surprising, record-breaking or unusual FACTS about {name} that most people would not know.
- These must be FACTUAL STATEMENTS — not activities or behaviours.
- GOOD examples: "First non-Guinean to receive the Officer of National Order of Merit award",
  "Known as the 'catfish' of the shipping industry", "Honorary Consul of Guinea in Singapore",
  "Owns the largest bauxite operation in the world".
- BAD examples (these go in DEMONSTRATED_INTERESTS): "enjoys hiking", "passionate about art",
  "proponent of green development" — these are interests/behaviours not facts.
- DO NOT include: career narrative (that goes in BIOGRAPHY).
- DO NOT include: donations (that goes in GIVING).
- DO NOT repeat anything that will be in DEMONSTRATED_INTERESTS.
"""

    if attr == "ADVERSE_NEWS":
        return base + f"""Specific rules for ADVERSE_NEWS:
- Start directly with the first adverse fact — do NOT start with meta-phrases like "The ADVERSE_NEWS section highlights..." or "This section covers...".
- Just write the facts directly e.g. "Sun Xiushun's operations in Guinea have faced criticism for..."
- Include ALL controversies, criticism, or negative press about {name} or their companies.
- Be factual and neutral — report exactly what the sources say.
- Only write "No adverse news found." if the sources genuinely contain zero negative content.
- Include: environmental criticism, community complaints, regulatory issues, legal disputes, corruption allegations.
"""

    if attr == "GIVING":
        return base + f"""Specific rules for GIVING:
- Include ALL concrete giving actions with specific details — be comprehensive, do not cut content.
- Always include numbers and amounts when mentioned — e.g. "2 hospitals", "500,000 yuan annually", "150 students".
- Include hospital counts, road projects, scholarship amounts, training programs, solar panels donated, community investments.
- DO NOT include vague future plans — only completed actions.
- DO NOT include business investments or company revenue.
- Write a full detailed paragraph — do not summarise or shorten, include every giving fact from the sources.
"""

    if attr == "POTENTIAL_CONNECTORS":
        return base + f"""Specific rules for POTENTIAL_CONNECTORS:
- Include ONLY business partners, co-investors, associates, board members, and key professional relationships of {name}.
- For each connector include their name and how they are connected to {name}.
- DO NOT include: immediate family members (wife, children, siblings, parents) — those go in FAMILY.
- DO NOT include: general mentions of companies without a specific named person.
- Focus on named individuals who could be useful professional connections.
"""

    if attr == "DEMONSTRATED_INTERESTS":
        return base + f"""Specific rules for DEMONSTRATED_INTERESTS:
- Include ONLY personal passions, causes {name} actively champions, and activities he does outside of core business.
- These are things he DOES or CARES ABOUT personally — not achievements or facts about him.
- GOOD examples: "Proponent of green shipping and clean energy",
  "Passionate about environmental sustainability in mining",
  "Advocate for community development in Guinea",
  "Interest in integrating renewable energy into industrial operations".
- BAD examples (these go in INTERESTING_FACTS): "First to receive X award", "Known as the catfish",
  "Honorary Consul" — these are facts not interests.
- DO NOT include: career narrative (BIOGRAPHY), donations (GIVING), or factual achievements (INTERESTING_FACTS).
- Focus on his VALUES, CAUSES and PERSONAL INTERESTS.
"""

    return base


# ── MERGE ONE ATTRIBUTE ───────────────────────────────────────────────────────

def merge_attribute(attr: str, chunks: list[dict], name: str) -> dict:
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
        # Truncate each chunk to 800 chars to keep prompts short and fast
        text = c["text"][:800] if len(c["text"]) > 800 else c["text"]
        sources_text += f"\nSource [{src_num}] ({c['source_url']}):\n{text}\n"

    source_list = "\n".join(f"[{i+1}] {url}" for i, url in enumerate(sources))
    prompt      = build_prompt(attr, name, sources_text, source_list)
    content     = ask_llm(prompt, num_predict=3000)

    print(f"    ✅ {attr:<25} merged ({len(chunks)} sources)")
    return {"attribute": attr, "content": content, "sources": sources}



    print(f"\n  Running cross-deduplication pass...")

    prompt = f"""You are reviewing 4 sections of a professional profile about {name}.
Your job is to deduplicate content across sections and ensure each fact appears in only one section.

Current content:

BIOGRAPHY:
{bio}

INTERESTING_FACTS:
{facts}

GIVING:
{giving}

DEMONSTRATED_INTERESTS:
{interests}

Rules:
- BIOGRAPHY: professional career story only.
- INTERESTING_FACTS: surprising FACTS and unique achievements — things he HAS DONE or HAS RECEIVED.
  e.g. "First non-Guinean to receive X award", "Known as the catfish of shipping", "Honorary Consul of Guinea".
- GIVING: donations, philanthropy, CSR with specific amounts and organisations ONLY.
- DEMONSTRATED_INTERESTS: personal VALUES, CAUSES and INTERESTS he champions.
  e.g. "Proponent of green shipping", "Passionate about sustainability", "Advocates for community development".
  These are things he BELIEVES IN or CARES ABOUT — not things he HAS DONE.

KEY RULE: If content appears in both INTERESTING_FACTS and DEMONSTRATED_INTERESTS — 
  ask yourself: is this a FACT about him (→ INTERESTING_FACTS) or something he CARES ABOUT (→ DEMONSTRATED_INTERESTS)?
  Move it to the correct section and remove from the other.

Instructions:
- STRICT RULE: Every piece of content must appear in EXACTLY ONE section. No exceptions.
- Go through each sentence/fact and decide which single section it belongs to.
- If the same content appears in multiple sections, keep it ONLY in the most appropriate one and DELETE it from all others.
- Do NOT add any new information not already present.
- Keep all inline citations [[N]] exactly as they are.

Section definitions (use these to decide):
- BIOGRAPHY: career story, professional journey, milestones.
- INTERESTING_FACTS: surprising FACTS — things he HAS received, IS known as, or HAS done that are unusual.
- GIVING: specific donations, charity amounts, CSR initiatives with organisations named.
- DEMONSTRATED_INTERESTS: personal VALUES and CAUSES he champions — things he BELIEVES IN or ADVOCATES FOR.

Return ONLY a JSON object with keys: BIOGRAPHY, INTERESTING_FACTS, GIVING, DEMONSTRATED_INTERESTS.
Each value is the cleaned paragraph text with citations retained.
Return ONLY valid JSON, no explanation, no markdown."""

    raw = ask_llm(prompt, num_predict=3000)

    # Parse JSON response
    raw = re.sub(r"```json|```", "", raw).strip()
    try:
        parsed = json.loads(raw)
        for key in ["BIOGRAPHY", "INTERESTING_FACTS", "GIVING", "DEMONSTRATED_INTERESTS"]:
            if key in parsed and parsed[key]:
                if key in results:
                    results[key]["content"] = parsed[key]
        print(f"    ✅ Cross-deduplication complete")
    except Exception as e:
        print(f"    ⚠️  Cross-deduplication parse failed: {e} — keeping original content")

    return results



# ── COMBINED FACTS + INTERESTS MERGE ─────────────────────────────────────────

def merge_facts_and_interests(facts_chunks: list, demo_chunks: list, name: str) -> tuple:
    """
    Merge INTERESTING_FACTS and DEMONSTRATED_INTERESTS in one LLM call.
    Classifies each piece of content into exactly one section — no overlap by design.
    """
    all_chunks = facts_chunks + [c for c in demo_chunks if c not in facts_chunks]

    if not all_chunks:
        empty = {"attribute": "", "content": None, "sources": []}
        return {**empty, "attribute": "INTERESTING_FACTS"}, {**empty, "attribute": "DEMONSTRATED_INTERESTS"}

    # Build sources list
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

    prompt = f"""You are classifying content about {name} into two sections for a professional profile.

Sources:
{sources_text}

Source reference list:
{source_list}

Classify ALL content into EXACTLY ONE of these two sections:

INTERESTING_FACTS — surprising, unique or notable FACTS about {name}:
- Things he HAS received, IS known as, or HAS done that are unusual or record-breaking
- Awards, titles, honours, records, unique achievements
- Examples: "Honorary Consul of the Republic of Guinea in Singapore",
  "Known as the catfish of the shipping industry",
  "First non-Guinean to receive Officer of National Order of Merit",
  "One of the largest foreign landowners in Guinea"

DEMONSTRATED_INTERESTS — personal VALUES, CAUSES and ACTIVITIES he champions:
- Things he BELIEVES IN, ADVOCATES FOR, or is PASSIONATE ABOUT
- Personal passions, causes, green initiatives, community development interests
- Examples: "Proponent of green shipping and methanol-ready vessels",
  "Passionate about sustainable mining practices",
  "Advocates for community development in Guinea"

STRICT RULES:
- Every piece of content goes in EXACTLY ONE section — never both
- Add inline citation [[N]] after each fact
- Write each section as a single cohesive paragraph
- Do NOT include career narrative (that goes in BIOGRAPHY)
- Do NOT include donations/CSR (that goes in GIVING)
- BOTH sections must have content if the sources provide enough information
- Look carefully for values, causes, and personal interests for DEMONSTRATED_INTERESTS

Return ONLY valid JSON:
{{"INTERESTING_FACTS": "paragraph with [[N]] citations or null", "DEMONSTRATED_INTERESTS": "paragraph with [[N]] citations or null"}}"""

    raw = ask_llm(prompt, num_predict=5000)
    raw = re.sub(r"```json|```", "", raw).strip()

    try:
        parsed = json.loads(raw)
        facts_content = parsed.get("INTERESTING_FACTS")
        demo_content  = parsed.get("DEMONSTRATED_INTERESTS")
        print(f"    ✅ INTERESTING_FACTS + DEMONSTRATED_INTERESTS merged together ({len(all_chunks)} sources)")
    except Exception as e:
        print(f"    ⚠️  Combined merge parse failed: {e}")
        facts_content = None
        demo_content  = None

    return (
        {"attribute": "INTERESTING_FACTS",     "content": facts_content, "sources": sources},
        {"attribute": "DEMONSTRATED_INTERESTS", "content": demo_content,  "sources": sources},
    )

# ── MAIN ──────────────────────────────────────────────────────────────────────

def run(attribute_buckets: dict, name: str) -> dict:
    buckets_to_merge = dict(attribute_buckets)

    # Pop INTERESTING_FACTS and DEMONSTRATED_INTERESTS — handle them together
    facts_chunks = buckets_to_merge.pop("INTERESTING_FACTS", [])
    demo_chunks  = buckets_to_merge.pop("DEMONSTRATED_INTERESTS", [])
    # If no separate demo chunks, use facts chunks for both
    if not demo_chunks:
        demo_chunks = facts_chunks

    print(f"\n  Running {len(buckets_to_merge)} parallel LLM merge calls + 1 combined facts/interests call...")

    results = {}

    # Run all other attributes in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        futures = {
            executor.submit(merge_attribute, attr, chunks, name): attr
            for attr, chunks in buckets_to_merge.items()
        }
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results[result["attribute"]] = result

    # Run combined INTERESTING_FACTS + DEMONSTRATED_INTERESTS in one call
    facts_result, demo_result = merge_facts_and_interests(facts_chunks, demo_chunks, name)
    results["INTERESTING_FACTS"]      = facts_result
    results["DEMONSTRATED_INTERESTS"] = demo_result

    # Fill missing attributes
    for attr in ATTRIBUTES + ["DEMONSTRATED_INTERESTS"]:
        if attr not in results:
            results[attr] = {"attribute": attr, "content": None, "sources": []}

    return results
