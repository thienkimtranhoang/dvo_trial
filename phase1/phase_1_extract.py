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
4. nationality — SOVEREIGN COUNTRY NAME ONLY e.g. "Singapore", "China", "United States".
   - NEVER return a province, state, city or region like "Shandong", "California", "Hong Kong Island".
   - If text says "born in Shandong, China" return "China".
   - If text says "Singaporean" return "Singapore".
5. net_worth — PERSONAL net worth only as "$X Billion" or "$X Million".
   - NEVER return company revenue, group assets, or market cap.
   - If both personal and company figures appear, return only the personal one.
6. net_worth_year — year the net worth figure is from as integer.
7. degree — full formal degree name only, NO abbreviations, NO brackets, NO honours suffix.
   - CORRECT: "Bachelor of Architecture", "Master of Business Administration", "Doctor of Philosophy"
   - WRONG: "B.Arch", "MBA", "PhD", "Bachelor of Architecture (Honours)", "Undergraduate degree", "Architect"
   - If the page mentions a degree, return the full formal name.
8. institution — full official university name only.
   - CORRECT: "University of Melbourne", "National University of Singapore"
   - WRONG: "NUS", "Melbourne Uni", "the university"
   - IMPORTANT: always look for the institution name in the SAME section as the degree on this page.
   - If multiple institutions appear together e.g. "Catholic High School, University of Melbourne",
     return ONLY the university name, not the school.
   - A university contains words like "University", "College", "Institute of Technology", "School of Business".

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
