from collections import defaultdict
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..")); from config import ATTRIBUTE_KEYWORDS


def tag_attributes(snippet: str) -> list:
    snippet_lower = snippet.lower()
    return [attr for attr, kws in ATTRIBUTE_KEYWORDS.items()
            if any(kw.lower() in snippet_lower for kw in kws)]


def run(all_results: list) -> dict:
    print(f"\n  Building URL → attributes map...")
    url_map = defaultdict(lambda: {"attributes": set(), "snippet": "", "url": ""})
    for result_list in all_results:
        for r in result_list:
            url = r.get("url", "")
            if not url:
                continue
            # Handle both individual (snippet) and org (content) result formats
            snippet = r.get("snippet") or r.get("content") or r.get("description") or ""
            url_map[url]["url"]     = url
            url_map[url]["snippet"] = snippet
            url_map[url]["attributes"].add(r.get("attribute", "BIOGRAPHY"))
            for tag in tag_attributes(snippet):
                url_map[url]["attributes"].add(tag)
    print(f"  Unique URLs found: {len(url_map)}")
    return dict(url_map)
