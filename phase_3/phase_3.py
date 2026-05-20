import json
import os
import sys
import subprocess
import phase_3_agent
import phase_3_collect


def run(phase2_output_path: str):
    # Load Phase 2 output
    with open(phase2_output_path, "r") as f:
        phase2_data = json.load(f)

    name    = phase2_data["name"]
    company = phase2_data.get("company", "")
    url_map = phase2_data["url_map"]
    
    print(f"\n{'═'*75}")
    print(f"  PHASE 3 — Parallel Scraping & Classified Extraction")
    print(f"  Name   : {name}")
    print(f"  Company: {company or 'Not provided'}")
    print(f"  URLs   : {len(url_map)}")
    print(f"{'═'*75}")

    # Step 1 — fire all agents in parallel
    agent_results = phase_3_agent.run(url_map, name)

    # Step 2 — collect and group by attribute
    attribute_buckets = phase_3_collect.run(agent_results)

    # Save output for Phase 4
    output = {
        "name":              name,
        "company":           company,
        "attribute_buckets": attribute_buckets,
    }

    output_path = os.path.join(os.path.dirname(__file__), "phase_3_output.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    total_chunks = sum(len(v) for v in attribute_buckets.values())
    print(f"\n  ✅ Phase 3 complete — {total_chunks} content chunks saved to phase_3_output.json")

    return output_path


if __name__ == "__main__":
    # Can be called directly or from phase_2.py
    if len(sys.argv) >= 2:
        phase2_path = sys.argv[1]
    else:
        phase2_path = os.path.join(os.path.dirname(__file__), "..", "phase_2", "phase_2_output.json")

    if not os.path.exists(phase2_path):
        print(f"ERROR: phase_2_output.json not found at {phase2_path}")
        print("Run phase_2/phase_2.py first.")
        sys.exit(1)

    output_path = run(phase2_path)

    # ── Auto chain to Phase 4 ─────────────────────────────────────────────────
    phase4_path = os.path.join(os.path.dirname(__file__), "..", "phase_4", "phase_4.py")
    if os.path.exists(phase4_path):
        print(f"\n  → Handing off to Phase 4...\n")
        subprocess.run([sys.executable, phase4_path, output_path], check=True)
    else:
        print(f"\n  ⚠️  Phase 4 not found at {phase4_path}")
        print(f"  Run phase_4/phase_4.py manually with phase_3_output.json")
