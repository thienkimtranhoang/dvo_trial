"""
Phase 2 Search — Organisation
Runs targeted Tavily searches for organisation profiles.
"""
import requests
import concurrent.futures
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import TAVILY_API_KEY

ORG_ATTRIBUTES = [
    "DATE_OF_ESTABLISHMENT",
    "BIOGRAPHY",
    "GIVING",
    "GIVING2",
    "GIVING3",
    "GIVING4",
    "GIVING5",
    "DEMONSTRATED_INTERESTS",
    "OTHER_INTERESTING_FACTS",
    "POTENTIAL_CONNECTORS",
    "ADVERSE_NEWS",
]

ORG_QUERIES = {
    "DATE_OF_ESTABLISHMENT":  "{name} founded established incorporated year history",
    "BIOGRAPHY":              "{name} company history overview background profile milestones executives",
    # Five giving queries from different angles
    "GIVING":                 '"{name}" donated gave scholarship bursary award',
    "GIVING2":                '"{name}" CSR programme grant foundation community contribution',
    "GIVING3":                '"{name}" million thousand donation education arts healthcare environment',
    "GIVING4":                '"{name}" received donation from donated to university polytechnic hospital charity',
    "GIVING5":                '"{name}" scholarship bursary award programme named fund established',
    "DEMONSTRATED_INTERESTS": "{name} programme initiative community interest annual event commitment values",
    "OTHER_INTERESTING_FACTS":"{name} achievement award record milestone acquisition partnership project",
    "POTENTIAL_CONNECTORS":   "{name} leadership board executives founders partners joint venture",
    "ADVERSE_NEWS":           "{name} controversy lawsuit scandal regulatory investigation criticism",
}


def tavily_search(query: str, attribute: str) -> list:
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {TAVILY_API_KEY}"},
            json={
                "query":              query,
                "search_depth":       "advanced",
                "max_results":        10,
                "include_raw_content": False,
            },
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        for r in results:
            r["attribute"] = attribute
        print(f"    [{attribute:<30}] → {len(results)} results")
        return results
    except Exception as e:
        print(f"    [{attribute:<30}] ERROR: {e}")
        return []


def run(name: str) -> list:
    print(f"\n  Running {len(ORG_QUERIES)} Tavily searches for organisation: {name}...")

    all_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=11) as executor:
        futures = {
            executor.submit(tavily_search, ORG_QUERIES[attr].format(name=name), attr): attr
            for attr in ORG_ATTRIBUTES
        }
        for future in concurrent.futures.as_completed(futures):
            all_results.extend(future.result())

    print(f"\n  Total raw results: {len(all_results)}")
    return all_results
