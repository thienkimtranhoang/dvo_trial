import json
import os
import sys
import subprocess
import phase_2_search
import phase_2_classify
import phase_2_rank
import phase_2_validate
import time

# ── INPUT — change these to run for different people ─────────────────────────
NAME    = "Daniel Teo Tong How"
COMPANY = None  # set to None if not available


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    t0 = time.time()

    # Allow passing name as command line argument
    if len(sys.argv) >= 2:
        NAME = sys.argv[1]
    if len(sys.argv) >= 3:
        COMPANY = sys.argv[2]

    print(f"\n{'═'*75}")
    print(f"  PHASE 2 — URL Collection & Classification")
    print(f"  Name   : {NAME}")
    print(f"  Company: {COMPANY or 'Not provided'}")
    print(f"{'═'*75}")

    # Step 1 — Search raw endpoints
    t1 = time.time()
    raw_results = phase_2_search.run(NAME, COMPANY)
    print(f"  [Timer] Search: {time.time() - t1:.1f}s")

    # Step 2 — Classify all raw results
    t2 = time.time()
    url_map = phase_2_classify.run(raw_results)
    print(f"  [Timer] Classify: {time.time() - t2:.1f}s")

    # Step 3 — Rank and take top 20 BEFORE validation
    # No point validating URLs that won't make the cut
    t3 = time.time()
    ranked = phase_2_rank.run(url_map, top_n=20)
    print(f"  [Timer] Rank: {time.time() - t3:.1f}s")

    # Step 4 — Flatten raw results and filter to top 20 URLs only
    top_urls = {r["url"] for r in ranked}

    flat_raw = []
    for item in raw_results:
        if isinstance(item, list):
            for sub in item:
                if isinstance(sub, dict):
                    flat_raw.append(sub)
        elif isinstance(item, dict):
            flat_raw.append(item)

    top_results = [item for item in flat_raw if item.get("url") in top_urls]

    # Step 5 — Validate ONLY the top 20 ranked URLs
    t4 = time.time()
    valid_results, rejected_results = phase_2_validate.run(top_results, NAME, COMPANY)
    print(f"  [Timer] Validate: {time.time() - t4:.1f}s")

    # Step 6 — Filter ranked list to validated URLs only and re-display
    valid_urls   = {r["url"] for r in valid_results}
    final_ranked = [r for r in ranked if r["url"] in valid_urls]
    phase_2_rank.display(final_ranked)

    # Save output for Phase 3
    output = {
        "name":    NAME,
        "company": COMPANY,
        "total":   len(final_ranked),
        "url_map": [
            {"url": r["url"], "attributes": r["attributes"], "coverage": r["coverage"]}
            for r in final_ranked
        ],
    }

    output_path = os.path.join(os.path.dirname(__file__), "phase_2_output.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n  ✅ Phase 2 complete — {len(final_ranked)} URLs saved to phase_2_output.json")
    print(f"  [Timer] Phase 2 total: {time.time() - t0:.1f}s")

    # ── Auto chain to Phase 3 ─────────────────────────────────────────────────
    phase3_path = os.path.join(os.path.dirname(__file__), "..", "phase_3", "phase_3.py")
    if os.path.exists(phase3_path):
        print(f"\n  → Handing off to Phase 3...\n")
        subprocess.run([sys.executable, phase3_path, output_path], check=True)
    else:
        print(f"\n  ⚠️  Phase 3 not found at {phase3_path}")
        print(f"  Run phase_3/phase_3.py manually with phase_2_output.json")