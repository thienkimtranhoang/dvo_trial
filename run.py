"""
DVO KYC Pipeline — Single Entry Point

Usage:
    python run.py                                          # prompts for input
    python run.py individual "Sun Xiushun" "Winning International Group"
    python run.py organisation "Mapletree Investments"
"""
import sys
import json
import os
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
import config

if not config.validate():
    sys.exit(1)


def save_json(data: dict, path: str):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_json(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def run_individual(NAME: str, COMPANY: str):
    """Run the individual profile pipeline."""

    print(f"\n{'═'*75}")
    print(f"  DVO KYC PIPELINE — INDIVIDUAL")
    print(f"  Name   : {NAME}")
    print(f"  Company: {COMPANY or 'Not provided'}")
    print(f"{'═'*75}")

    # ── PHASE 2 ───────────────────────────────────────────────────────────────
    print(f"\n{'═'*75}")
    print(f"  PHASE 2 — URL Collection & Classification")
    print(f"{'═'*75}")
    sys.path.insert(0, str(ROOT / "phase_2"))
    import phase_2_search, phase_2_classify, phase_2_rank, phase_2_validate
    raw_results = phase_2_search.run(NAME, COMPANY)

    print(f"\n  Validating search results...")
    valid_results, rejected = phase_2_validate.run(raw_results, NAME, COMPANY)
    print(f"  ✅ {len(valid_results)} valid, {len(rejected)} rejected")

    url_map = phase_2_classify.run([valid_results])
    ranked  = phase_2_rank.run(url_map, top_n=20)
    phase_2_rank.display(ranked)
    phase2_output = {
        "name": NAME, "company": COMPANY, "total": len(ranked),
        "url_map": [{"url": r["url"], "attributes": r["attributes"], "coverage": r["coverage"]} for r in ranked]
    }
    save_json(phase2_output, str(ROOT / "phase_2" / "phase_2_output.json"))
    print(f"\n  ✅ Phase 2 complete — {len(ranked)} URLs")

    # ── PHASE 3 ───────────────────────────────────────────────────────────────
    print(f"\n{'═'*75}")
    print(f"  PHASE 3 — Parallel Scraping & Classified Extraction")
    print(f"{'═'*75}")
    sys.path.insert(0, str(ROOT / "phase_3"))
    import phase_3_agent, phase_3_collect
    agent_results     = phase_3_agent.run(phase2_output["url_map"], NAME)
    attribute_buckets = phase_3_collect.run(agent_results)
    phase3_output     = {"name": NAME, "company": COMPANY, "attribute_buckets": attribute_buckets}
    save_json(phase3_output, str(ROOT / "phase_3" / "phase_3_output.json"))
    total_chunks = sum(len(v) for v in attribute_buckets.values())
    print(f"\n  ✅ Phase 3 complete — {total_chunks} content chunks")

    # ── PHASE 4 ───────────────────────────────────────────────────────────────
    print(f"\n{'═'*75}")
    print(f"  PHASE 4 — LLM Merging per Attribute")
    print(f"{'═'*75}")
    sys.path.insert(0, str(ROOT / "phase_4"))
    import phase_4_merge, phase_4_extract
    merged  = phase_4_merge.run(attribute_buckets, NAME)
    phase4_results = {
        attr: {"content": r["content"], "sources": r["sources"]}
        for attr, r in merged.items()
    }
    save_json({"name": NAME, "company": COMPANY, "results": phase4_results},
              str(ROOT / "phase_4" / "phase_4_output.json"))
    print(f"\n  ✅ Phase 4 complete")

    # ── PHASE 4 EXTRACT ───────────────────────────────────────────────────────
    print(f"\n{'═'*75}")
    print(f"  PHASE 4 EXTRACT — Shallow Attributes from Biography")
    print(f"{'═'*75}")
    shallow, phase4_results = phase_4_extract.run(phase4_results, NAME)
    save_json({"name": NAME, "company": COMPANY, "results": phase4_results},
              str(ROOT / "phase_4" / "phase_4_output.json"))

    # ── PHASE 1 — Nationality always + missing fields ─────────────────────────
    missing_fields = [f for f in ["age", "net_worth", "education"]
                      if not shallow.get(f) or shallow.get(f) == []]
    phase1_fields  = missing_fields + ["nationality"]

    print(f"\n{'═'*75}")
    print(f"  PHASE 1 — Nationality (always) + Missing: {missing_fields}")
    print(f"{'═'*75}")
    sys.path.insert(0, str(ROOT / "phase_1"))
    import phase_1
    phase1_output = phase_1.run(NAME, COMPANY, fields=phase1_fields)

    field_to_src = {
        "age":         "age_source",
        "nationality": "nat_source",
        "net_worth":   "nw_source",
        "education":   "edu_source",
    }

    if phase1_output.get("nationality"):
        shallow["nationality"] = phase1_output["nationality"]
        shallow["nat_source"]  = phase1_output.get("nat_source", "")
        print(f"  ✅ nationality: {shallow['nationality']}")

    for field in missing_fields:
        val = phase1_output.get(field)
        if val and val != [] and val is not None:
            if not shallow.get(field) or shallow.get(field) == []:
                shallow[field] = val
                src_key = field_to_src.get(field)
                if src_key and phase1_output.get(src_key):
                    shallow[src_key] = phase1_output[src_key]
                print(f"  ✅ {field} filled from Phase 1")

    shallow["name"] = NAME
    phase1_output   = shallow
    save_json(phase1_output, str(ROOT / "phase_1" / "phase_1_output.json"))
    print(f"\n  ✅ Shallow attributes complete")

    # ── PHASE 5 ───────────────────────────────────────────────────────────────
    print(f"\n{'═'*75}")
    print(f"  PHASE 5 — Post-processing")
    print(f"{'═'*75}")
    sys.path.insert(0, str(ROOT / "phase_5"))
    import phase_5
    phase4_for_p5 = {"name": NAME, "company": COMPANY, "results": phase4_results}
    phase5_output = phase_5.run(phase4_for_p5)
    phase5_output["name"] = NAME
    save_json(phase5_output, str(ROOT / "phase_5" / "phase_5_output.json"))
    print(f"\n  ✅ Phase 5 complete")

    # ── PHASE 5 IMAGE ─────────────────────────────────────────────────────────
    print(f"\n{'═'*75}")
    print(f"  PHASE 5 IMAGE — Photo Search")
    print(f"{'═'*75}")
    import phase_5_image
    photo_path = phase_5_image.search_and_download(NAME)

    # ── PHASE 6 ───────────────────────────────────────────────────────────────
    print(f"\n{'═'*75}")
    print(f"  PHASE 6 — Document Generation")
    print(f"{'═'*75}")
    sys.path.insert(0, str(ROOT / "phase_6"))
    import phase_6
    doc_path = phase_6.run(phase1_output, phase5_output, photo_path)

    print(f"\n{'═'*75}")
    print(f"  ✅ PIPELINE COMPLETE — INDIVIDUAL")
    print(f"  Name    : {NAME}")
    print(f"  Document: {doc_path}")
    print(f"{'═'*75}\n")


def run_organisation(NAME: str):
    """Run the organisation profile pipeline."""

    print(f"\n{'═'*75}")
    print(f"  DVO KYC PIPELINE — ORGANISATION")
    print(f"  Name: {NAME}")
    print(f"{'═'*75}")

    # ── PHASE 2 ───────────────────────────────────────────────────────────────
    print(f"\n{'═'*75}")
    print(f"  PHASE 2 — URL Collection")
    print(f"{'═'*75}")
    sys.path.insert(0, str(ROOT / "phase_2"))
    from phase_2_search_org import run as org_search
    from phase_2_rank       import run as rank, display as rank_display
    from config import ORG_ATTRIBUTE_KEYWORDS

    raw_results = org_search(NAME)

    # Validate results — ensure they are actually about this organisation
    from phase_2_validate_org import run as org_validate
    valid_results, rejected_results = org_validate(raw_results, NAME)
    raw_results = valid_results

    # Org-specific classify using ORG_ATTRIBUTE_KEYWORDS
    from collections import defaultdict
    url_map = defaultdict(lambda: {"attributes": set(), "snippet": "", "url": ""})
    for r in raw_results:
        url = r.get("url", "")
        if not url:
            continue
        snippet = r.get("snippet") or r.get("content") or r.get("description") or ""
        url_map[url]["url"]     = url
        url_map[url]["snippet"] = snippet
        url_map[url]["attributes"].add(r.get("attribute", "BIOGRAPHY"))
        snippet_lower = snippet.lower()
        for attr, kws in ORG_ATTRIBUTE_KEYWORDS.items():
            if any(kw.lower() in snippet_lower for kw in kws):
                url_map[url]["attributes"].add(attr)
    url_map = dict(url_map)
    print(f"  Unique URLs found: {len(url_map)}")

    ranked  = rank(url_map, top_n=20, org_mode=True)
    rank_display(ranked, org_mode=True)
    phase2_output = {
        "name": NAME, "company": None, "total": len(ranked),
        "url_map": [{"url": r["url"], "attributes": r["attributes"], "coverage": r["coverage"]} for r in ranked]
    }
    save_json(phase2_output, str(ROOT / "phase_2" / "phase_2_output.json"))
    print(f"\n  ✅ Phase 2 complete — {len(ranked)} URLs")

    # ── PHASE 3 ───────────────────────────────────────────────────────────────
    print(f"\n{'═'*75}")
    print(f"  PHASE 3 — Parallel Scraping")
    print(f"{'═'*75}")
    sys.path.insert(0, str(ROOT / "phase_3"))
    from phase_3_agent_org import run as org_agent
    import phase_3_collect

    agent_results     = org_agent(phase2_output["url_map"], NAME)
    attribute_buckets = phase_3_collect.run(agent_results, org_mode=True)
    save_json({"name": NAME, "attribute_buckets": attribute_buckets},
              str(ROOT / "phase_3" / "phase_3_output.json"))
    total_chunks = sum(len(v) for v in attribute_buckets.values())
    print(f"\n  ✅ Phase 3 complete — {total_chunks} content chunks")

    # ── PHASE 4 ───────────────────────────────────────────────────────────────
    print(f"\n{'═'*75}")
    print(f"  PHASE 4 — LLM Merging")
    print(f"{'═'*75}")
    sys.path.insert(0, str(ROOT / "phase_4"))
    from phase_4_merge_org import run as org_merge

    merged = org_merge(attribute_buckets, NAME)
    phase4_results = {
        attr: {"content": r["content"], "sources": r["sources"]}
        for attr, r in merged.items()
    }
    phase4_output = {"name": NAME, "results": phase4_results}
    save_json(phase4_output, str(ROOT / "phase_4" / "phase_4_output.json"))
    print(f"\n  ✅ Phase 4 complete")

    # ── PHASE 6 ───────────────────────────────────────────────────────────────
    print(f"\n{'═'*75}")
    print(f"  PHASE 6 — Document Generation")
    print(f"{'═'*75}")
    sys.path.insert(0, str(ROOT / "phase_6"))
    from phase_6_org import run as org_doc

    doc_path = org_doc(phase4_output)

    print(f"\n{'═'*75}")
    print(f"  ✅ PIPELINE COMPLETE — ORGANISATION")
    print(f"  Name    : {NAME}")
    print(f"  Document: {doc_path}")
    print(f"{'═'*75}\n")


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":

    # Parse args or prompt user
    if len(sys.argv) >= 2:
        PROFILE_TYPE = sys.argv[1].lower()
        NAME         = sys.argv[2] if len(sys.argv) >= 3 else ""
        COMPANY      = sys.argv[3] if len(sys.argv) >= 4 else ""
    else:
        print(f"\n{'═'*75}")
        print(f"  DVO KYC PIPELINE")
        print(f"{'═'*75}")
        print(f"  Profile type:")
        print(f"    1. individual")
        print(f"    2. organisation")
        PROFILE_TYPE = input("\n  Enter type (individual/organisation): ").strip().lower()
        if PROFILE_TYPE in ("1", "i", "ind"):
            PROFILE_TYPE = "individual"
        elif PROFILE_TYPE in ("2", "o", "org"):
            PROFILE_TYPE = "organisation"
        NAME    = input("  Enter name: ").strip()
        COMPANY = ""
        if PROFILE_TYPE == "individual":
            COMPANY = input("  Enter company name (optional, press Enter to skip): ").strip()

    if PROFILE_TYPE == "individual":
        run_individual(NAME, COMPANY)
    elif PROFILE_TYPE in ("organisation", "organization"):
        run_organisation(NAME)
    else:
        print(f"  ❌ Unknown profile type: {PROFILE_TYPE}")
        print(f"     Use 'individual' or 'organisation'")
        sys.exit(1)
