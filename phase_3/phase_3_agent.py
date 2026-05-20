import json
import re
import requests
import concurrent.futures
from config import TINYFISH_API_KEY

AGENT_URL = "https://agent.tinyfish.ai/v1/automation/run"

ALL_ATTRIBUTES = [
    "BIOGRAPHY", "FAMILY", "INTERESTING_FACTS", "ADVERSE_NEWS",
    "GIVING", "POTENTIAL_CONNECTORS", "KEY_POSITIONS",
]


def build_prompt(name: str, attributes: list[str]) -> str:
    attrs_list = "\n".join(f"- {a}" for a in attributes)
    attrs_keys = ", ".join(f'"{a}"' for a in attributes)
    return f"""Extract specific information about {name} from this webpage.

You must extract ONLY these fields:
{attrs_list}

Instructions:
- Be fast and efficient. Read the visible page content immediately.
- Stay on this page only. Do NOT click links or navigate away.
- Do NOT wait for slow-loading elements — read what is visible.
- Only extract information explicitly about {name} — ignore other people.
- For each field write a clean factual summary of what you found.
- If a field is not on this page return null for that field.
- Return ONLY a JSON object, no explanation, no markdown.

Return format:
{{{attrs_keys.replace('"', '"')}}}
Where each value is a factual text string or null."""


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
            timeout=300,
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

        found = [k for k, v in result.items() if v and str(v).lower() != "null"] if isinstance(result, dict) else []
        print(f"    ✅ {domain:<40} → {found if found else 'nothing extracted'}")

        return {"url": url, "attributes": attributes, "extracted": result if isinstance(result, dict) else {}}

    except Exception as e:
        print(f"    ❌ {domain:<40} → {str(e)[:60]}")
        return {"url": url, "attributes": attributes, "extracted": {}}


def run(url_map: list[dict], name: str) -> list[dict]:
    print(f"\n  Firing {len(url_map)} parallel TinyFish Agent calls...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda u: run_agent(u, name), url_map))
    successful = sum(1 for r in results if r["extracted"])
    print(f"\n  Completed: {successful}/{len(url_map)} pages extracted")
    return results
