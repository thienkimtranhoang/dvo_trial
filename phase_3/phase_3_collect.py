from collections import defaultdict

ATTRIBUTES = [
    "BIOGRAPHY", "FAMILY", "INTERESTING_FACTS", "ADVERSE_NEWS",
    "GIVING", "POTENTIAL_CONNECTORS", "KEY_POSITIONS",
]


def run(agent_results: list[dict]) -> dict:
    print(f"\n  Collecting and grouping results by attribute...")
    buckets = defaultdict(list)

    for result in agent_results:
        url       = result["url"]
        extracted = result.get("extracted", {})
        for attr in ATTRIBUTES:
            value = extracted.get(attr)
            if value and str(value).lower() != "null" and str(value).strip():
                buckets[attr].append({"text": value, "source_url": url})

    print(f"\n  ATTRIBUTE BUCKET SUMMARY")
    print(f"{'─'*55}")
    for attr in ATTRIBUTES:
        count = len(buckets.get(attr, []))
        print(f"  {attr:<25} {'█' * count} ({count} sources)")
    print(f"{'─'*55}")

    return dict(buckets)
