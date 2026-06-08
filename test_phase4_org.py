"""
Test script — reruns Phase 4 and Phase 6 for organisation profile
using existing phase_3_output.json.

Run from the dvo_pipeline folder:
    python test_phase4_org.py
"""
import sys
import json
import os
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "phase_6"))
sys.path.insert(0, str(ROOT / "phase_4"))
sys.path.insert(0, str(ROOT / "phase_3"))
sys.path.insert(0, str(ROOT))

import config

def load(path):
    with open(path) as f:
        return json.load(f)

phase3_path = ROOT / "phase_3" / "phase_3_output.json"
if not phase3_path.exists():
    print(f"❌ Missing: {phase3_path}")
    sys.exit(1)

phase3_data       = load(phase3_path)
NAME              = phase3_data.get("name", "Unknown")
attribute_buckets = phase3_data.get("attribute_buckets", {})

print(f"\n{'═'*75}")
print(f"  TEST ORG — Phase 4 + Phase 6")
print(f"  Name: {NAME}")
print(f"{'═'*75}")
print(f"\n  Loaded {sum(len(v) for v in attribute_buckets.values())} chunks from Phase 3")

print(f"\n  ATTRIBUTE BUCKET SUMMARY")
print(f"{'─'*55}")
for attr, chunks in sorted(attribute_buckets.items()):
    print(f"  {attr:<30} {'█' * min(len(chunks), 20)} ({len(chunks)} sources)")
print(f"{'─'*55}")

# ── Phase 4 ───────────────────────────────────────────────────────────────────
print(f"\n{'═'*75}")
print(f"  PHASE 4 — LLM Merging")
print(f"{'═'*75}")

from phase_4_merge_org import run as org_merge

merged = org_merge(dict(attribute_buckets), NAME)

# Build phase4_results safely
phase4_results = {}
for attr, r in merged.items():
    if r is None:
        phase4_results[attr] = {"content": None, "sources": []}
    elif isinstance(r, dict):
        phase4_results[attr] = {
            "content": r.get("content"),
            "sources": r.get("sources", [])
        }
    else:
        phase4_results[attr] = {"content": str(r) if r else None, "sources": []}

phase4_output = {"name": NAME, "results": phase4_results}

with open(ROOT / "phase_4" / "phase_4_output.json", "w") as f:
    json.dump(phase4_output, f, indent=2)

print(f"\n  ✅ Phase 4 complete")
print(f"\n  SECTION SUMMARY")
print(f"{'─'*55}")
for attr, data in phase4_results.items():
    content = data.get("content") or ""
    status  = f"✅ {len(content)} chars" if content else "⚠️  empty"
    print(f"  {attr:<30} {status}")
print(f"{'─'*55}")

# ── Phase 6 ───────────────────────────────────────────────────────────────────
print(f"\n{'═'*75}")
print(f"  PHASE 6 — Document Generation")
print(f"{'═'*75}")

from phase_6_org import run as org_doc

doc_path = org_doc(phase4_output)

print(f"\n{'═'*75}")
print(f"  ✅ DONE")
print(f"  Document: {doc_path}")
print(f"{'═'*75}\n")
