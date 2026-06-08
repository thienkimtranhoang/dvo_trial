"""
Test script — runs ONLY Phase 6 using existing phase_1 and phase_5 output JSONs.
Run from the dvo_pipeline folder:
    python test_phase6.py
"""
import sys
import json
import os
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "phase_5"))
sys.path.insert(0, str(ROOT / "phase_6"))

import config

def load(path):
    with open(path) as f:
        return json.load(f)

# Load existing outputs
phase1_path = ROOT / "phase_1" / "phase_1_output.json"
phase5_path = ROOT / "phase_5" / "phase_5_output.json"
photo_path  = ROOT / "phase_5" / "photo.jpg"

if not phase1_path.exists():
    print(f"❌ Missing: {phase1_path}")
    sys.exit(1)
if not phase5_path.exists():
    print(f"❌ Missing: {phase5_path}")
    sys.exit(1)

phase1_output = load(phase1_path)
phase5_output = load(phase5_path)
NAME = phase5_output.get("name", phase1_output.get("name", "Unknown"))

print(f"\n{'═'*65}")
print(f"  TEST — Phase 6 only")
print(f"  Name: {NAME}")
print(f"{'═'*65}")

# ── Phase 6 ───────────────────────────────────────────────────────────────────
print(f"\n{'═'*65}")
print(f"  PHASE 6 — Document Generation")
print(f"{'═'*65}")

import phase_6

photo = str(photo_path) if photo_path.exists() else None
doc_path = phase_6.run(phase1_output, phase5_output, photo)

print(f"\n{'═'*65}")
print(f"  ✅ DONE")
print(f"  Document: {doc_path}")
print(f"{'═'*65}\n")
