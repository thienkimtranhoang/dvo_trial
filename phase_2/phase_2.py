import json
import os
import sys
import subprocess
import phase_2_search
import phase_2_classify
import phase_2_rank

# ── INPUT — change these to run for different people ─────────────────────────
NAME    = "Sun Xiushun"
COMPANY = "Winning International Group"  # set to None if not available


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
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

    # Step 1 — search
    raw_results = phase_2_search.run(NAME, COMPANY)

    # Step 2 — classify
    url_map = phase_2_classify.run(raw_results)

    # Step 3 — rank
    ranked = phase_2_rank.run(url_map, top_n=20)
    phase_2_rank.display(ranked)

    # Save output for Phase 3
    output = {
        "name":    NAME,
        "company": COMPANY,
        "total":   len(ranked),
        "url_map": [
            {"url": r["url"], "attributes": r["attributes"], "coverage": r["coverage"]}
            for r in ranked
        ],
    }

    output_path = os.path.join(os.path.dirname(__file__), "phase_2_output.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n  ✅ Phase 2 complete — {len(ranked)} URLs saved to phase_2_output.json")

    # ── Auto chain to Phase 3 ─────────────────────────────────────────────────
    phase3_path = os.path.join(os.path.dirname(__file__), "..", "phase_3", "phase_3.py")
    if os.path.exists(phase3_path):
        print(f"\n  → Handing off to Phase 3...\n")
        subprocess.run([sys.executable, phase3_path, output_path], check=True)
    else:
        print(f"\n  ⚠️  Phase 3 not found at {phase3_path}")
        print(f"  Run phase_3/phase_3.py manually with phase_2_output.json")
