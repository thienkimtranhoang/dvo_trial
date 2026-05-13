import concurrent.futures
from phase_1_utils import (
    TINYFISH_API_KEY, TAVILY_API_KEY,
    is_bad_source, is_useless,
)
import requests


# ── TINYFISH SEARCH ───────────────────────────────────────────────────────────

def tf_search(query: str) -> list:
    try:
        resp = requests.get(
            "https://api.search.tinyfish.ai",
            params={"query": query},
            headers={"X-API-Key": TINYFISH_API_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        return [r["url"] for r in resp.json().get("results", []) if r.get("url")]
    except Exception as e:
        print(f"    [TF SEARCH ERROR] {e}")
        return []


def tf_fetch(url: str) -> dict | None:
    try:
        resp = requests.post(
            "https://api.fetch.tinyfish.ai",
            headers={"X-API-Key": TINYFISH_API_KEY, "Content-Type": "application/json"},
            json={"urls": [url]},
            timeout=60,
        )
        resp.raise_for_status()
        data    = resp.json()
        results = data.get("results", [])
        errors  = data.get("errors", [])
        if results and results[0].get("text") and not is_useless(results[0]["text"]):
            return {"url": url, "text": results[0]["text"], "method": "tinyfish"}
        if errors:
            print(f"    [TF BLOCKED] {url[:60]}")
    except Exception as e:
        print(f"    [TF ERROR] {url[:60]} → {e}")
    return None


def run_tinyfish(name: str, company: str = None) -> list:
    queries = [
        f"{name} biography",
        f"{name} age date of birth born",
        f"{name} nationality citizenship country",
        f"{name} personal net worth wealth",
        f"{name} education university degree graduated",
    ]
    if company:
        queries.append(f"{name} {company} background profile")

    print(f"\n  [TinyFish] Searching the web — running {len(queries)} queries in parallel...")
    with concurrent.futures.ThreadPoolExecutor() as executor:
        url_lists = list(executor.map(tf_search, queries))

    seen = set()
    urls = []
    for ul in url_lists:
        for url in ul:
            if url not in seen and not is_bad_source(url):
                seen.add(url)
                urls.append(url)
    urls = urls[:15]

    print(f"  [TinyFish] Found {len(urls)} unique URLs — fetching full page content...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        results = list(executor.map(tf_fetch, urls))

    pages = [r for r in results if r]
    print(f"  [TinyFish] Successfully fetched {len(pages)}/{len(urls)} pages ✓")
    return pages


# ── TAVILY SEARCH ─────────────────────────────────────────────────────────────

def tv_search(label_query: tuple) -> list:
    label, query = label_query
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {TAVILY_API_KEY}"},
            json={"query": query, "search_depth": "basic", "max_results": 5},
            timeout=15,
        )
        resp.raise_for_status()
        snippets = []
        for r in resp.json().get("results", []):
            url     = r.get("url", "")
            content = r.get("content", "")
            if url and content and not is_bad_source(url) and not is_useless(content):
                snippets.append({"url": url, "text": content, "method": "tavily", "label": label})
        return snippets
    except Exception as e:
        print(f"    [TAVILY ERROR] {label} → {e}")
        return []


def run_tavily(name: str, company: str = None) -> list:
    queries = [
        ("DOB",         f"{name} date of birth born year"),
        ("DOB_SITE",    f"site:prabook.com {name}"),
        ("NATIONALITY", f"{name} nationality citizenship"),
        ("NET_WORTH",   f"{name} net worth wealth"),
        ("EDUCATION",   f"{name} education university degree"),
        ("EDU_SITE",    f"site:tatlerasia.com {name}"),
        ("BIOGRAPHY",   f"{name} biography background"),
    ]
    if company:
        queries.append(("COMPANY", f"{name} {company}"))

    print(f"\n  [Tavily] Searching for snippets — running {len(queries)} targeted queries in parallel...")
    with concurrent.futures.ThreadPoolExecutor() as executor:
        all_snippets = list(executor.map(tv_search, queries))

    pages = []
    for snippet_list in all_snippets:
        pages.extend(snippet_list)

    print(f"  [Tavily] Retrieved {len(pages)} snippets ✓")
    return pages
