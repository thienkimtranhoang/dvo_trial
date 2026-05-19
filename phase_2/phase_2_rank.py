from collections import defaultdict
from config import ATTRIBUTES


def run(url_map: dict, top_n: int = 20) -> list[dict]:
    print(f"\n  Ranking by attribute coverage, taking top {top_n}...")

    ranked = [
        {"url": url, "attributes": sorted(list(data["attributes"])),
         "coverage": len(data["attributes"]), "snippet": data["snippet"]}
        for url, data in url_map.items()
    ]
    ranked.sort(key=lambda x: x["coverage"], reverse=True)

    # ── Fix 1: Max 2 URLs per domain ─────────────────────────────────────────
    domain_count = defaultdict(int)
    deduped = []
    for r in ranked:
        domain = r["url"].split("/")[2] if "/" in r["url"] else r["url"]
        if domain_count[domain] < 2:
            domain_count[domain] += 1
            deduped.append(r)

    # ── Fix 2: Ensure top 5 cover all 7 attributes at least twice ────────────
    # Take initial top 5
    selected   = deduped[:5]
    remaining  = deduped[5:]

    def coverage_count(urls):
        counts = defaultdict(int)
        for r in urls:
            for a in r["attributes"]:
                counts[a] += 1
        return counts

    # Check which attributes need more coverage in top 5
    counts = coverage_count(selected)
    missing = [a for a in ATTRIBUTES if counts.get(a, 0) < 2]

    if missing:
        print(f"  Top 5 missing coverage for: {missing} — boosting...")
        # Find best URLs from remaining that cover missing attributes
        for attr in missing:
            for r in remaining:
                if attr in r["attributes"] and r not in selected:
                    # Swap out lowest coverage URL in selected that doesn't help
                    selected.append(r)
                    remaining.remove(r)
                    counts = coverage_count(selected)
                    if counts.get(attr, 0) >= 2:
                        break

    # Fill rest up to top_n from remaining
    final = selected + [r for r in remaining if r not in selected]
    final = final[:top_n]

    print(f"  Final: {len(final)} unique URLs ({len(set(r['url'].split('/')[2] for r in final))} domains)")
    return final


def display(ranked: list[dict]):
    print(f"\n{'═'*75}")
    print(f"  PHASE 2 RESULTS — Top {len(ranked)} URLs")
    print(f"{'═'*75}\n")
    for r in ranked:
        parts     = r["url"].split("/")
        domain    = parts[2] if len(parts) > 2 else r["url"]
        path      = "/" + parts[3] if len(parts) > 3 else ""
        short_url = f"{domain}{path}..."
        attrs     = "[" + ", ".join(r["attributes"]) + "]"
        print(f"  {short_url:<45} → {attrs}")

    print(f"\n{'═'*75}")
    print(f"\n  ATTRIBUTE COVERAGE")
    print(f"{'─'*55}")
    attr_counts = defaultdict(int)
    for r in ranked:
        for a in r["attributes"]:
            attr_counts[a] += 1
    for attr in ATTRIBUTES:
        count = attr_counts.get(attr, 0)
        print(f"  {attr:<25} {'█' * count} ({count} URLs)")
    print(f"{'═'*75}")
