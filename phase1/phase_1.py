import sys
from phase_1_utils    import fmt_source
from phase_1_search   import run_tinyfish, run_tavily
from phase_1_extract  import extract_all
from phase_1_aggregate import aggregate
from phase_1_validate import validate_all
# ── CONFIG — change these before running ──────────────────────────────────────
NAME    = "Sun Xiushun"
COMPANY = ""   # optional — leave as "" if not available


# ── DISPLAY ───────────────────────────────────────────────────────────────────

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


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Allow passing name from command line: python phase_1.py "Tim Cook" "Apple"
    if len(sys.argv) >= 2:
        NAME = sys.argv[1]
    if len(sys.argv) >= 3:
        COMPANY = sys.argv[2]

    print(f"\n{'='*65}")
    print(f"  PHASE 1 — Person Research Pipeline")
    print(f"  Name   : {NAME}")
    print(f"  Company: {COMPANY or 'Not provided'}")
    print(f"{'='*65}")

    # ── Step 1: Search ────────────────────────────────────────────────────────
    print(f"\n  STEP 1/4 — Searching for relevant pages...")
    tf_pages = run_tinyfish(NAME, COMPANY)
    tv_pages = run_tavily(NAME, COMPANY)

    # Deduplicate — keep longest version per URL
    seen = {}
    for p in tf_pages + tv_pages:
        url = p["url"]
        if url not in seen or len(p["text"]) > len(seen[url]["text"]):
            seen[url] = p
    all_pages = list(seen.values())
    print(f"\n  Deduplicated to {len(all_pages)} unique pages "
          f"(TinyFish: {len(tf_pages)} full pages + Tavily: {len(tv_pages)} snippets)")

    # ── Step 1.5: Validate ────────────────────────────────────────────────   # ← ADD
    print(f"\n  STEP 2/5 — Validating pages are about the right person...")    # ← ADD
    all_pages, rejected = validate_all(all_pages, NAME, COMPANY)               # ← ADD
    if not all_pages:                                                           # ← ADD
        print(f"\n  ✗ No valid pages found — aborting.")                       # ← ADD
        sys.exit(1)     
        
    # ── Step 2: Extract ───────────────────────────────────────────────────────
    print(f"\n  STEP 2/4 — Extracting structured data from each page...")
    extractions = extract_all(all_pages, NAME)

    # ── Step 3: Aggregate ─────────────────────────────────────────────────────
    print(f"\n  STEP 3/4 — Aggregating results using frequency & credibility logic...")
    result = aggregate(extractions, NAME)

    # ── Step 4: Display ───────────────────────────────────────────────────────
    print(f"\n  STEP 4/4 — Final results:")
    display(NAME, result)
