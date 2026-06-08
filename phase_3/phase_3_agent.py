import json
import re
import requests
import concurrent.futures
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import TINYFISH_API_KEY

AGENT_URL = "https://agent.tinyfish.ai/v1/automation/run"

ALL_ATTRIBUTES = [
    "BIOGRAPHY", "FAMILY", "INTERESTING_FACTS", "ADVERSE_NEWS",
    "GIVING", "POTENTIAL_CONNECTORS",
]

FIELD_DESCRIPTIONS = {
    "BIOGRAPHY": "career history, early life, professional background and major milestones of {name}",

    "FAMILY": """personal family information about {name}:
  - Spouse or partner name and any personal details
  - Children: names, count, any details mentioned
  - Parents: names and occupations if mentioned
  - Siblings: names and relationship
  - Any personal family background or upbringing
  Write what you find as a natural paragraph. Only blood relatives and spouse — NOT business partners.""",

    "INTERESTING_FACTS": """surprising, unique or notable FACTS about {name}:
  - Awards, honours, titles received (e.g. Honorary Consul, Officer of National Order)
  - Records or firsts (e.g. first non-Guinean to receive X award)
  - Nicknames or reputation (e.g. known as the catfish of shipping)
  - Unusual achievements or milestones
  NOT hobbies or personal interests — those go in DEMONSTRATED_INTERESTS.""",

    "ADVERSE_NEWS": """any negative, critical or controversial information about {name} or their companies:
  - Environmental damage, pollution, water contamination caused by operations
  - Complaints from local communities about projects
  - Regulatory violations, government investigations, sanctions
  - Lawsuits, legal disputes, court cases
  - Fraud, corruption, bribery allegations
  - Labour rights violations, worker exploitation, safety incidents, fatalities
  - Criticism from NGOs, journalists, governments or international organisations
  - Negative media coverage of business practices
  Be thorough — extract ALL critical or negative content found on this page. Do NOT soften it.""",

    "GIVING": """philanthropic and CSR activities by {name} or their company:
  - Specific donations with amounts (e.g. 500,000 yuan annually)
  - Infrastructure built for communities (hospitals, roads, schools) with numbers
  - Scholarship programs with number of beneficiaries
  - Training programs, solar panels donated, any community investment
  Include specific numbers and organisation names wherever mentioned.""",

    "POTENTIAL_CONNECTORS": """named business partners, co-investors, associates of {name}:
  - Specific named individuals and how they are connected
  - Companies partnered with and the nature of the partnership
  - Government officials connected to {name}
  NOT family members — those go in FAMILY.""",
}


def build_prompt(name: str, attributes: list[str]) -> str:
    fields_desc = ""
    for attr in attributes:
        desc = FIELD_DESCRIPTIONS.get(attr, attr.lower().replace("_", " "))
        try:
            desc = desc.format(name=name)
        except Exception:
            pass
        fields_desc += f"\n\n{attr}:\n{desc}"

    attrs_keys = ", ".join(f'"{a}": "text or null"' for a in attributes)

    return f"""Extract specific information about {name} from this webpage.

Extract ONLY these fields:{fields_desc}

General instructions:
- Read the ENTIRE visible page content thoroughly before extracting.
- Be comprehensive — extract ALL relevant facts for each field, do not summarise or skip details.
- Include specific numbers, names, dates, amounts wherever they appear.
- Stay on this page only. Do NOT click external links or navigate away.
- Only extract information explicitly about {name} — ignore unrelated content.
- For each field write a detailed factual paragraph with everything found — do not cut content short.
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
                "goal":            build_prompt(name, attributes),
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

        # Unwrap {"result": ...} wrapper if present
        if isinstance(result, dict) and list(result.keys()) == ["result"]:
            inner = result["result"]
            if isinstance(inner, str):
                try:
                    result = json.loads(re.sub(r"```json|```", "", inner).strip())
                except Exception:
                    result = {}
            elif isinstance(inner, dict):
                result = inner

        found = [k for k, v in result.items() if v and str(v).lower() != "null"] if isinstance(result, dict) else []
        print(f"    ✅ {domain:<40} → {found if found else 'nothing extracted'}")
        return {"url": url, "attributes": attributes, "extracted": result if isinstance(result, dict) else {}}

    except Exception as e:
        print(f"    ❌ {domain:<40} → {str(e)[:60]}")
        return {"url": url, "attributes": attributes, "extracted": {}}


def run(url_map: list[dict], name: str) -> list[dict]:
    print(f"\n  Firing {len(url_map)} parallel TinyFish Agent calls...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(lambda u: run_agent(u, name), url_map))
    successful = sum(1 for r in results if r["extracted"])
    print(f"\n  Completed: {successful}/{len(url_map)} pages extracted")
    return results
