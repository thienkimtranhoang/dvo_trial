import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from phase_1_utils     import fmt_source
from phase_1_search    import run_tinyfish, run_tavily
from phase_1_extract   import extract_all
from phase_1_aggregate import aggregate
from phase_1_validate  import validate_all

# ── CONFIG ────────────────────────────────────────────────────────────────────
NAME    = "Sun Xiushun"
COMPANY = ""


def display(name: str, result: dict):
    print(f"\n{'='*65}")
    print(f"  RESULTS: {name}")
    print(f"{'='*65}")

    age = result.get("age")
    src = fmt_source(result.get("age_source"))
    if age:
        print(f"  Age         : {age}" + (f" | {src}" if src else ""))
    else:
        print(f"  Age         : Not found")

    nat = result.get("nationality")
    src = fmt_source(result.get("nat_source"))
    if nat:
        print(f"  Nationality : {nat}" + (f" | {src}" if src else ""))
    else:
        print(f"  Nationality : Not found")

    nw  = result.get("net_worth")
    yr  = result.get("nw_year")
    src = fmt_source(result.get("nw_source"))
    if nw:
        display_nw = f"{nw} ({yr})" if yr else nw
        print(f"  Net Worth   : {display_nw}" + (f" | {src}" if src else ""))
    else:
        print(f"  Net Worth   : Not found")

    degrees = result.get("education", [])
    if degrees:
        print(f"  Education   :")
        for d in degrees:
            src = fmt_source(d.get("source"))
            print(f"    - {d['degree']}, {d['institution']}" + (f" | {src}" if src else ""))
    else:
        print(f"  Education   : Not found")

    print(f"{'='*65}\n")


def run(name: str, company: str = "", fields: list = None) -> dict:
    """Run Phase 1 and return structured result dict."""
    print(f"\n  STEP 1/4 — Searching for relevant pages (fields: {fields or 'all'})...")
    tf_pages = run_tinyfish(name, company, fields=fields)
    tv_pages = run_tavily(name, company, fields=fields)

    # Deduplicate
    seen = {}
    for p in tf_pages + tv_pages:
        url = p["url"]
        if url not in seen or len(p["text"]) > len(seen[url]["text"]):
            seen[url] = p
    all_pages = list(seen.values())
    print(f"\n  Deduplicated to {len(all_pages)} unique pages")

    # Validate
    print(f"\n  STEP 2/4 — Validating pages...")
    all_pages, rejected = validate_all(all_pages, name, company)
    if not all_pages:
        print(f"\n  ✗ No valid pages found.")
        return {"name": name}

    # Extract
    print(f"\n  STEP 3/4 — Extracting structured data...")
    extractions = extract_all(all_pages, name)

    # Aggregate
    print(f"\n  STEP 4/4 — Aggregating results...")
    result = aggregate(extractions, name)
    result["name"] = name

    display(name, result)
    return result


if __name__ == "__main__":
    if len(sys.argv) >= 2: NAME    = sys.argv[1]
    if len(sys.argv) >= 3: COMPANY = sys.argv[2]

    print(f"\n{'='*65}")
    print(f"  PHASE 1 — Person Research Pipeline")
    print(f"  Name   : {NAME}")
    print(f"  Company: {COMPANY or 'Not provided'}")
    print(f"{'='*65}")

    run(NAME, COMPANY)
