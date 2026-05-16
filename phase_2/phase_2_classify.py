from collections import defaultdict
from config import ATTRIBUTE_KEYWORDS


def tag_attributes(snippet: str) -> list[str]:
    snippet_lower = snippet.lower()
    return [attr for attr, kws in ATTRIBUTE_KEYWORDS.items()
            if any(kw.lower() in snippet_lower for kw in kws)]


def run(all_results: list[list[dict]]) -> dict:
    print(f"\n  Building URL → attributes map...")
    url_map = defaultdict(lambda: {"attributes": set(), "snippet": "", "url": ""})
    for result_list in all_results:
        for r in result_list:
            url = r["url"]
            url_map[url]["url"]     = url
            url_map[url]["snippet"] = r["snippet"]
            url_map[url]["attributes"].add(r["attribute"])
            for tag in tag_attributes(r["snippet"]):
                url_map[url]["attributes"].add(tag)
    print(f"  Unique URLs found: {len(url_map)}")
    return dict(url_map)
