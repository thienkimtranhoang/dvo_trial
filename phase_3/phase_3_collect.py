from collections import defaultdict

INDIVIDUAL_ATTRIBUTES = [
    "BIOGRAPHY", "FAMILY", "INTERESTING_FACTS", "ADVERSE_NEWS",
    "GIVING", "POTENTIAL_CONNECTORS", "DEMONSTRATED_INTERESTS",
]

ORG_ATTRIBUTES = [
    "DATE_OF_ESTABLISHMENT", "BIOGRAPHY", "GIVING",
    "DEMONSTRATED_INTERESTS", "OTHER_INTERESTING_FACTS",
    "POTENTIAL_CONNECTORS", "ADVERSE_NEWS",
]


def run(agent_results: list, org_mode: bool = False) -> dict:
    print(f"\n  Collecting and grouping results by attribute...")
    buckets    = defaultdict(list)
    attributes = ORG_ATTRIBUTES if org_mode else INDIVIDUAL_ATTRIBUTES

    for result in agent_results:
        url       = result["url"]
        extracted = result.get("extracted", {})
        # Collect all keys from extracted — not just pre-defined attributes
        for attr, value in extracted.items():
            if value and str(value).lower() != "null" and str(value).strip():
                buckets[attr].append({"text": value, "source_url": url})

    # Merge secondary buckets
    if "GIVING2" in buckets:
        for item in buckets.pop("GIVING2"):
            buckets["GIVING"].append(item)

    if "GIVING2" in buckets:
        if "GIVING" not in buckets:
            buckets["GIVING"] = []
        for item in buckets.pop("GIVING2"):
            buckets["GIVING"].append(item)

    # Also handle legacy DONATION_HISTORY key
    if "DONATION_HISTORY" in buckets:
        if "GIVING" not in buckets:
            buckets["GIVING"] = []
        for item in buckets.pop("DONATION_HISTORY"):
            buckets["GIVING"].append(item)

    # Merge GIVING3 and GIVING4 into GIVING
    for key in ["GIVING3", "GIVING4", "GIVING5"]:
        if key in buckets:
            if "GIVING" not in buckets:
                buckets["GIVING"] = []
            for item in buckets.pop(key):
                buckets["GIVING"].append(item)

    print(f"\n  ATTRIBUTE BUCKET SUMMARY")
    print(f"{'─'*55}")
    for attr in attributes:
        count = len(buckets.get(attr, []))
        print(f"  {attr:<30} {'█' * min(count, 20)} ({count} sources)")
    print(f"{'─'*55}")

    total = sum(len(v) for v in buckets.values())
    print(f"\n  ✅ Phase 3 complete — {total} content chunks")

    return dict(buckets)
