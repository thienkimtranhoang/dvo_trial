import json
import os
import sys
import phase_4_merge
from config import ATTRIBUTES


def display_results(name: str, merged: dict):
    print(f"\n{'═'*75}")
    print(f"  FINAL RESULTS: {name}")
    print(f"{'═'*75}")

    for attr in ATTRIBUTES:
        result  = merged.get(attr, {})
        content = result.get("content")
        sources = result.get("sources", [])

        print(f"\n  {attr}")
        print(f"  {'─'*60}")

        if content:
            # Print paragraph with word wrap
            words   = content.split()
            line    = "  "
            for word in words:
                if len(line) + len(word) + 1 > 73:
                    print(line)
                    line = "  " + word + " "
                else:
                    line += word + " "
            if line.strip():
                print(line)

            # Print numbered source list
            if sources:
                print(f"")
                for i, url in enumerate(sources, 1):
                    print(f"  [{i}] {url}")
        else:
            print(f"  No information found.")

    print(f"\n{'═'*75}\n")


def run(phase3_output_path: str):
    with open(phase3_output_path, "r") as f:
        phase3_data = json.load(f)

    name              = phase3_data["name"]
    company           = phase3_data.get("company", "")
    attribute_buckets = phase3_data["attribute_buckets"]

    print(f"\n{'═'*75}")
    print(f"  PHASE 4 — LLM Merging per Attribute")
    print(f"  Name   : {name}")
    print(f"  Company: {company or 'Not provided'}")
    print(f"  Attributes with content: {len(attribute_buckets)}")
    print(f"{'═'*75}")

    # Merge all attributes in parallel
    merged = phase_4_merge.run(attribute_buckets, name)

    # Save output
    output = {
        "name":    name,
        "company": company,
        "results": {
            attr: {"content": r["content"], "sources": r["sources"]}
            for attr, r in merged.items()
        }
    }

    output_path = os.path.join(os.path.dirname(__file__), "phase_4_output.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n  ✅ Phase 4 complete — saved to phase_4_output.json")

    # Display final results
    display_results(name, merged)

    return output_path


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        phase3_path = sys.argv[1]
    else:
        phase3_path = os.path.join(os.path.dirname(__file__), "..", "phase_3", "phase_3_output.json")

    if not os.path.exists(phase3_path):
        print(f"ERROR: phase_3_output.json not found at {phase3_path}")
        print("Run phase_3/phase_3.py first.")
        sys.exit(1)

    run(phase3_path)
