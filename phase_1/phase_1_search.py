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


FIELD_QUERIES = {
    "age":         lambda n, c: f"{n}{c} age date of birth born year",
    "nationality": lambda n, c: f"{n}{c} nationality citizenship country",
    "net_worth":   lambda n, c: f"{n}{c} personal net worth wealth billion",
    "education":   lambda n, c: f"{n}{c} education university degree graduated",
}


def run_tinyfish(name: str, company: str = None, fields: list = None) -> list:
    c = f" {company}" if company else ""
    # If specific fields requested, only run those queries
    if fields:
        queries = [FIELD_QUERIES[f](name, c) for f in fields if f in FIELD_QUERIES]
        queries.append(f"{name}{c} biography")  # always include biography
    else:
        queries = [
            f"{name}{c} biography",
            f"{name}{c} age date of birth born",
            f"{name}{c} nationality citizenship country",
            f"{name}{c} personal net worth wealth",
            f"{name}{c} education university degree graduated",
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


TAVILY_FIELD_QUERIES = {
    "age":         [("DOB", "{n}{c} date of birth born year"), ("DOB_SITE", "site:prabook.com {n}")],
    "nationality": [
        ("NATIONALITY",  "{n}{c} nationality citizenship country of origin"),
        ("NAT_CITIZEN",  "{n}{c} citizen citizenship passport holds"),
        ("NAT_PROFILE",  "{n}{c} profile biography born"),
    ],
    "net_worth":   [("NET_WORTH", "{n}{c} net worth billion million rich"), ("NET_WORTH2", "{n}{c} forbes bloomberg wealth ranking")],
    "education":   [("EDUCATION", "{n}{c} education university degree graduated"), ("EDU_SITE", "site:tatlerasia.com {n}")],
}


def run_tavily(name: str, company: str = None, fields: list = None) -> list:
    c = f" {company}" if company else ""
    n = name

    if fields:
        queries = [("BIOGRAPHY", f"{n}{c} biography background")]
        for f in fields:
            for label, q_template in TAVILY_FIELD_QUERIES.get(f, []):
                queries.append((label, q_template.format(n=n, c=c)))
    else:
        queries = [
            ("DOB",         f"{n}{c} date of birth born year"),
            ("DOB_SITE",    f"site:prabook.com {n}"),
            ("NATIONALITY", f"{n}{c} nationality citizenship"),
            ("NET_WORTH",   f"{n}{c} net worth billion million rich"),
            ("NET_WORTH2",  f"{n}{c} forbes bloomberg wealth ranking"),
            ("EDUCATION",   f"{n}{c} education university degree graduated"),
            ("EDU_SITE",    f"site:tatlerasia.com {n}"),
            ("BIOGRAPHY",   f"{n}{c} biography background"),
        ]
        if company:
            queries.append(("COMPANY", f"{n} {company}"))

    print(f"\n  [Tavily] Searching for snippets — running {len(queries)} targeted queries in parallel...")
    with concurrent.futures.ThreadPoolExecutor() as executor:
        all_snippets = list(executor.map(tv_search, queries))

    pages = []
    for snippet_list in all_snippets:
        pages.extend(snippet_list)

    print(f"  [Tavily] Retrieved {len(pages)} snippets ✓")
    return pages
