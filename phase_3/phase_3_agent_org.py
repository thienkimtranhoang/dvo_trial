"""
Phase 3 Agent — Organisation
TinyFish agent calls for organisation profile extraction.
"""
import json
import re
import requests
import concurrent.futures
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import TINYFISH_API_KEY

AGENT_URL = "https://agent.tinyfish.ai/v1/automation/run"

ORG_FIELD_DESCRIPTIONS = {
    "DATE_OF_ESTABLISHMENT": """when {name} was founded, established or incorporated:
  - Exact founding date, month and year, or year only
  - Country or city of incorporation
  - Any rebranding or restructuring dates""",

    "BIOGRAPHY": """history and background of {name} as an organisation:
  - Founding story, origin and inspiration behind the organisation
  - Who founded it and why — include memorial or legacy context if relevant
  - Core mission and what the organisation does
  - Named properties, assets, funds, programmes managed (list them all)
  - Key milestones, growth history and current scale
  - Geographic presence — which markets, cities, countries
  - Named board members, executives and their titles
  - Any budget formulas or financial commitments (e.g. S$1M per S$500M profit)
  - CSR pillars or strategic focus areas
  Be as detailed as possible — include all specific named items from the page""",

    "GIVING": """ALL philanthropic and CSR activities of {name} with full details:
  - Extract EVERY donation mentioned — do not skip any
  - For each donation include: exact year, exact amount (S$ or US$), recipient organisation full name, purpose
  - Group by category if possible: Education, Arts, Healthcare, Environment, Community
  - Include scholarships, bursaries, foundations, named programmes, infrastructure projects
  - Include in-kind donations (e.g. medical masks, trees) with quantities
  - Include named programmes like "Mapletree Sustainability Programme" or "TENG Scholarship"
  - Do NOT include NUS-related giving""",

    "DEMONSTRATED_INTERESTS": """specific programmes, initiatives and causes that {name} actively champions:
  - Named recurring annual programmes or events the organisation runs
  - Internal initiatives and community projects with specific details
  - Plans or commitments announced for future activities
  - Alumni networks, beneficiary programmes, community engagement plans
  - Specific causes championed with concrete examples
  - Do NOT write generic sector names — look for specific named programmes and activities""",

    "OTHER_INTERESTING_FACTS": """unique, specific and notable facts about {name} not covered elsewhere:
  - Very specific one-off facts: "adopted a village in X", "first organisation to Y"
  - Named partnerships with specific organisations for specific projects
  - Awards, rankings, firsts, records with exact details
  - Specific events supported (name, year, consecutive years)
  - Acquisitions, deals with exact values and locations
  - Any fact that is surprising or highly specific to this organisation
  - Do NOT repeat biography or giving content""",

    "POTENTIAL_CONNECTORS": """key individuals and organisations connected to {name}:
  - Named founders, executives, board members with titles
  - Strategic partners, joint venture partners, co-investors
  - Government bodies or institutions with formal relationships
  - Format as 'Name — Title/Role (relationship to organisation)'
  - Exclude employees without strategic significance""",

    "ADVERSE_NEWS": """any negative, critical or controversial information about {name}:
  - Lawsuits, legal disputes, regulatory violations
  - Environmental damage, community complaints
  - Fraud, corruption or bribery allegations
  - Criticism from NGOs, governments, media or affected communities
  - Be thorough — extract ALL negative content found. Do NOT soften it.""",
}


def build_org_prompt(name: str, attributes: list) -> str:
    fields_desc = ""
    for attr in attributes:
        desc = ORG_FIELD_DESCRIPTIONS.get(attr, attr.lower().replace("_", " "))
        try:
            desc = desc.format(name=name)
        except Exception:
            pass
        fields_desc += f"\n\n{attr}:\n{desc}"

    attrs_keys = ", ".join(f'"{a}": "text or null"' for a in attributes)

    return f"""Extract specific information about the organisation {name} from this webpage.

Extract ONLY these fields:{fields_desc}

General instructions:
- Read the ENTIRE visible page content thoroughly before extracting.
- Be comprehensive and precise — extract ALL relevant facts, especially specific numbers, amounts, dates and named items.
- Never summarise when you can include the specific detail — names, dollar amounts, years, programme names matter.
- IMPORTANT: Stay on THIS page only. Do NOT click any links. Do NOT navigate to other pages.
- IMPORTANT: Do NOT scroll to external links or navigate away — read only what is on this page.
- Only extract information explicitly about {name} — ignore unrelated content.
- For each field write a detailed factual paragraph with everything found on this page.
- If a field is not mentioned on this page return null for that field.
- Return ONLY a JSON object, no explanation, no markdown.

Return format:
{{{attrs_keys}}}"""


def run_agent(url_entry: dict, name: str) -> dict:
    url        = url_entry["url"]
    attributes = url_entry["attributes"]
    domain     = url.split("/")[2] if "/" in url else url

    try:
        resp = requests.post(
            AGENT_URL,
            headers={"X-API-Key": TINYFISH_API_KEY, "Content-Type": "application/json"},
            json={
                "url":             url,
                "goal":            build_org_prompt(name, attributes),
                "browser_profile": "stealth",
            },
            timeout=600,
        )
        resp.raise_for_status()
        data   = resp.json()
        result = data.get("result", {})

        if isinstance(result, str):
            result = re.sub(r"```json|```", "", result).strip()
            try:
                result = json.loads(result)
            except Exception:
                result = {}

        # If agent wrapped response in {"result": "..."} unwrap it
        if isinstance(result, dict) and list(result.keys()) == ["result"]:
            inner = result["result"]
            if isinstance(inner, str):
                inner = re.sub(r"```json|```", "", inner).strip()
                try:
                    result = json.loads(inner)
                except Exception:
                    result = {}
            elif isinstance(inner, dict):
                result = inner

        # Filter to only known org field keys
        if isinstance(result, dict):
            org_keys = {"DATE_OF_ESTABLISHMENT", "BIOGRAPHY", "GIVING", "GIVING2",
                        "DEMONSTRATED_INTERESTS", "OTHER_INTERESTING_FACTS",
                        "POTENTIAL_CONNECTORS", "ADVERSE_NEWS"}
            result = {k: v for k, v in result.items() if k in org_keys and v and str(v).lower() != "null"}

        found = list(result.keys()) if isinstance(result, dict) else []
        print(f"    ✅ {domain:<40} → {found if found else 'nothing extracted'}")
        return {"url": url, "attributes": attributes, "extracted": result if isinstance(result, dict) else {}}

    except Exception as e:
        print(f"    ❌ {domain:<40} → {str(e)[:60]}")
        return {"url": url, "attributes": attributes, "extracted": {}}


def run(url_map: list, name: str) -> list:
    print(f"\n  Firing {len(url_map)} parallel TinyFish Agent calls...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(lambda u: run_agent(u, name), url_map))

    successful = sum(1 for r in results if r["extracted"])
    print(f"\n  Completed: {successful}/{len(url_map)} pages extracted")
    return results
