import requests
import concurrent.futures
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..")); from config import TAVILY_API_KEY, BAD_SOURCES, build_queries


def is_bad_source(url: str) -> bool:
    return any(b in url.lower() for b in BAD_SOURCES)


def tavily_search(attr_query: tuple) -> list[dict]:
    attr, query = attr_query
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {TAVILY_API_KEY}"},
            json={"query": query, "search_depth": "advanced", "max_results": 10},
            timeout=20,
        )
        resp.raise_for_status()
        results = []
        for r in resp.json().get("results", []):
            url     = r.get("url", "")
            snippet = r.get("content", "")
            if url and snippet and not is_bad_source(url):
                results.append({"url": url, "snippet": snippet, "attribute": attr})
        print(f"    [{attr:<22}] → {len(results)} results")
        return results
    except Exception as e:
        print(f"    [{attr:<22}] ERROR → {e}")
        return []


def run(name: str, company: str = None) -> list[list[dict]]:
    queries = build_queries(name, company)
    print(f"\n  Running {len(queries)} Tavily advanced searches in parallel...")
    with concurrent.futures.ThreadPoolExecutor() as executor:
        all_results = list(executor.map(tavily_search, queries))
    total = sum(len(r) for r in all_results)
    print(f"\n  Total raw results: {total}")
    return all_results
