import concurrent.futures
from phase_1_utils import ask_llm, parse_json, fmt_source


# ── EXTRACTION PROMPT ─────────────────────────────────────────────────────────

def _build_prompt(name: str, url: str, text: str) -> str:
    return f"""You are extracting specific facts about {name} from a webpage.

Source URL: {url}

Page content:
{text}

Instructions:
- ONLY extract what is EXPLICITLY written on this page about {name}.
- Do NOT guess, infer, or hallucinate anything.
- If a field is NOT clearly stated on this page, return null.

Field rules:
1. dob — date of birth in format "Month DD, YYYY" e.g. "February 22, 1943". Only if explicitly stated.
2. age — age as integer e.g. 83. Only if explicitly stated as a number on this page.
3. article_year — IMPORTANT: Search the ENTIRE page for ANY date. Look in bylines, footers, headers,
   "Published:", "Updated:", "Posted:", copyright notices, URL paths (e.g. /2023/), timestamps, photo captions.
   Examples: "Oct 23, 2011" → 2011, "August 7, 2020" → 2020, "/2023/" in URL → 2023.
   Return as 4-digit integer. You MUST return a year if ANY date exists on the page.
4. nationality — CURRENT CITIZENSHIP only, as a sovereign country name e.g. "Singapore", "China".
   - NEVER return a province, state, city or region like "Shandong", "California", "Hong Kong".
   - Nationality means CURRENT CITIZENSHIP — not birthplace.
   - Someone can be born in China but be a Singaporean citizen — return Singapore in that case.
   - Priority order (use highest available):
     1. Explicit citizenship: "Singaporean citizen", "holds Singapore citizenship", "Singapore passport"
     2. Official role implying citizenship: "Singapore's ambassador", "Singapore PR"
     3. Long-term residence with context: "has lived in Singapore for X years", "based in Singapore since"
     4. Birthplace only if nothing else found: "born in China"
   - If page says "moved to Singapore" or "settled in Singapore" — strongly prefer Singapore over birthplace.
   - NEVER infer nationality just because someone works or does business in a country.
5. net_worth — PERSONAL net worth only formatted as "$X Billion" or "$X Million".
   - Look carefully for ANY of these patterns:
     * "net worth of $X", "worth $X billion", "estimated personal fortune of $X"
     * "billionaire worth $X", "ranked X with wealth of $X"
     * Forbes/Bloomberg personal wealth rankings with a dollar figure next to the person name
   - CRITICAL: NEVER return project values, mine values, infrastructure costs or company revenues.
     e.g. "The $23 billion Simandou project" is NOT personal net worth — it is a project value.
     e.g. "Winning International Group revenue of $5 billion" is NOT personal net worth.
     Only return a figure if it is explicitly described as the PERSON's personal wealth or net worth.
   - If no clearly personal net worth figure exists on this page, return null.
   - Normalise: always "$X Billion" or "$X Million" e.g. "$2.8 Billion".
6. net_worth_year — the year the net worth figure was reported. Look for article date near the figure.
7. degree — full formal degree name only, NO abbreviations, NO brackets.
   - CORRECT: "Bachelor of Engineering", "Master of Business Administration", "Bachelor of Science in Maritime Studies"
   - WRONG: "B.Eng", "MBA", "BSc", "Honours", "Undergraduate degree", "Diploma"
   - Maritime schools: "studied at Jiangsu Maritime Institute" → degree "Bachelor of Maritime Studies", institution "Jiangsu Maritime Institute"
   - Military colleges: "Anhui Military College" → degree "Military Science", institution "Anhui Military College"
   - Vocational schools: if only a vocational/trade school is mentioned, still extract it with degree "Diploma"
   - If only "graduated from X university" with no degree name → degree "Graduate", institution "X University"
8. institution — full official name of the school, college or university.
   - CORRECT: "University of Melbourne", "Jiangsu Maritime Institute", "Fudan University", "Anhui Military College"
   - WRONG: "NUS", "Melbourne Uni", "the university", "his school"
   - Extract the institution even if the degree type is unclear.
   - If multiple schools mentioned, return the HIGHEST level (university beats high school).

Return ONLY a JSON object, no explanation, no markdown:
{{
  "dob": "Month DD, YYYY" or null,
  "age": integer or null,
  "article_year": integer or null,
  "nationality": "Country" or null,
  "net_worth": "$X Billion" or null,
  "net_worth_year": integer or null,
  "degree": "full formal degree name" or null,
  "institution": "full university name" or null
}}"""


# ── PER-PAGE EXTRACTION ───────────────────────────────────────────────────────

def extract_from_page(page: dict, name: str) -> dict:
    url    = page["url"]
    text   = page["text"]
    prompt = _build_prompt(name, url, text)
    raw    = ask_llm(prompt)
    result = parse_json(raw)
    if isinstance(result, dict):
        result["source"] = url
    return result if isinstance(result, dict) else {"source": url}


# ── BATCH EXTRACTION ──────────────────────────────────────────────────────────

def extract_all(pages: list, name: str) -> list:
    print(f"\n  [LLM] Sending {len(pages)} pages to local model for extraction — running in parallel...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(pages)) as executor:
        results = list(executor.map(lambda p: extract_from_page(p, name), pages))

    print(f"\n{'='*65}")
    print(f"  LLM EXTRACTION RESULTS PER PAGE")
    print(f"{'='*65}")
    found_count = 0
    for r in results:
        src    = r.get("source", "")
        domain = src.split("/")[2] if "/" in src else src
        fields = {k: v for k, v in r.items() if k != "source" and v is not None and str(v).lower() != "null"}
        if fields:
            found_count += 1
            print(f"\n  [{domain}]")
            for k, v in fields.items():
                print(f"    {k}: {v}")
        else:
            print(f"\n  [{domain}] — nothing found")
    print(f"\n  [LLM] Extraction complete — {found_count}/{len(results)} pages had useful data ✓")
    print(f"{'='*65}")
    return results
