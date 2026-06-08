"""
Test script — runs from Phase 4 output onwards:
Phase 4 Extract → Phase 5 → Phase 5 Image → Phase 6

Run from the dvo_pipeline folder:
    python test_phase56.py
"""
import sys
import json
import os
from pathlib import Path

ROOT = Path(__file__).parent
# Insert ROOT first so root config.py is found before phase config shims
sys.path.insert(0, str(ROOT / "phase_4"))
sys.path.insert(0, str(ROOT / "phase_5"))
sys.path.insert(0, str(ROOT / "phase_6"))
sys.path.insert(0, str(ROOT))

import config

def load(path):
    with open(path) as f:
        return json.load(f)

# Check required files
phase4_path = ROOT / "phase_4" / "phase_4_output.json"
photo_path  = ROOT / "phase_5" / "photo.jpg"

if not phase4_path.exists():
    print(f"❌ Missing: {phase4_path}")
    print("   Run the full pipeline first to generate phase_4_output.json")
    sys.exit(1)

phase4_data    = load(phase4_path)
NAME           = phase4_data.get("name", "Unknown")
COMPANY        = phase4_data.get("company", "")
phase4_results = phase4_data.get("results", {})

print(f"\n{'═'*75}")
print(f"  TEST — Phase 4 Extract → Phase 5 → Phase 6")
print(f"  Name: {NAME}")
print(f"{'═'*75}")

# ── Phase 4 Extract ───────────────────────────────────────────────────────────
print(f"\n{'═'*75}")
print(f"  PHASE 4 EXTRACT — Shallow Attributes from Biography")
print(f"{'═'*75}")

import phase_4_extract
shallow, phase4_results = phase_4_extract.run(phase4_results, NAME)

# Check missing and load from phase_1_output if available
missing = [f for f in ["age", "nationality", "net_worth", "education"]
           if not shallow.get(f) or shallow.get(f) == []]

phase1_path = ROOT / "phase_1" / "phase_1_output.json"
if missing and phase1_path.exists():
    print(f"\n  Missing {missing} — loading from Phase 1 output...")
    phase1_data = load(phase1_path)
    field_to_src = {"age": "age_source", "nationality": "nat_source",
                    "net_worth": "nw_source", "education": "edu_source"}
    for field in missing:
        if shallow.get(field) is None or shallow.get(field) == []:
            val = phase1_data.get(field)
            if val and val != []:
                shallow[field] = val
                src_key = field_to_src.get(field)
                if src_key and phase1_data.get(src_key):
                    shallow[src_key] = phase1_data[src_key]
                print(f"    ✅ {field} loaded from Phase 1")

shallow["name"] = NAME
phase1_output   = shallow

# Save updated phase_4_output
with open(ROOT / "phase_4" / "phase_4_output.json", "w") as f:
    json.dump({"name": NAME, "company": COMPANY, "results": phase4_results}, f, indent=2)

# ── Phase 5 ───────────────────────────────────────────────────────────────────
print(f"\n{'═'*75}")
print(f"  PHASE 5 — Biography Cleaning")
print(f"{'═'*75}")

import phase_5
phase4_for_p5 = {"name": NAME, "company": COMPANY, "results": phase4_results}
phase5_output = phase_5.run(phase4_for_p5)
phase5_output["name"] = NAME

with open(ROOT / "phase_5" / "phase_5_output.json", "w") as f:
    json.dump(phase5_output, f, indent=2)
print(f"\n  ✅ Phase 5 complete")

# ── Phase 5 Image ─────────────────────────────────────────────────────────────
print(f"\n{'═'*75}")
print(f"  PHASE 5 IMAGE — Photo Search")
print(f"{'═'*75}")

import phase_5_image
photo = phase_5_image.search_and_download(NAME)

# ── Phase 6 ───────────────────────────────────────────────────────────────────
print(f"\n{'═'*75}")
print(f"  PHASE 6 — Document Generation")
print(f"{'═'*75}")

import phase_6
doc_path = phase_6.run(phase1_output, phase5_output, photo)

print(f"\n{'═'*75}")
print(f"  ✅ DONE")
print(f"  Document: {doc_path}")
print(f"{'═'*75}\n")
