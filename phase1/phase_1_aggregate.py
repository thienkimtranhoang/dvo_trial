import re
import json
import datetime
from collections import Counter, defaultdict
from phase_1_utils import ask_llm, fmt_source, strip_honours, CURRENT_YEAR


# ── AGE HELPERS ───────────────────────────────────────────────────────────────

def normalise_age(age, article_year) -> int | None:
    if age is None:
        return None
    try:
        age = int(age)
        if article_year:
            return age + (CURRENT_YEAR - int(article_year))
        return age
    except Exception:
        return None


def age_from_dob(dob_str) -> int | None:
    if not dob_str:
        return None
    today = datetime.date.today()
    for fmt in ("%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y", "%Y-%m-%d"):
        try:
            dob = datetime.datetime.strptime(dob_str.strip(), fmt).date()
            return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        except ValueError:
            pass
    m = re.search(r'\b(19\d{2}|20\d{2})\b', str(dob_str))
    if m:
        return today.year - int(m.group(1))
    return None


# ── DEGREE LEVEL HELPER ───────────────────────────────────────────────────────

def degree_level(d: str) -> str:
    dl = d.lower()
    if any(w in dl for w in ["doctor", "ph.d", "phd"]):
        return "phd"
    if any(w in dl for w in ["master", "mba", "m.sc", "msc"]):
        return "master"
    if any(w in dl for w in ["bachelor", "undergraduate", "b.sc", "bsc", "b.a"]):
        return "bachelor"
    return "other"


# ── MAIN AGGREGATION ──────────────────────────────────────────────────────────

def aggregate(extractions: list, name: str) -> dict:
    print(f"\n{'='*65}")
    print(f"  AGGREGATING RESULTS")
    print(f"{'='*65}")

    # ── AGE ───────────────────────────────────────────────────────────────────
    print(f"\n  [Age] Calculating from DOB and age mentions...")
    age_pool = []  # (normalised_age, source, kind, original_age)

    for e in extractions:
        src = e.get("source", "")

        dob = e.get("dob")
        if dob and str(dob).lower() != "null":
            a = age_from_dob(dob)
            if a:
                age_pool.append((a, src, "dob", a))
                print(f"    DOB '{dob}' → age {a} | {fmt_source(src)}")

        age = e.get("age")
        if age and str(age).lower() != "null":
            a = normalise_age(age, e.get("article_year"))
            if a:
                age_pool.append((a, src, "number", int(age)))
                print(f"    Age {age} (article {e.get('article_year')}) → normalised {a} | {fmt_source(src)}")

    if age_pool:
        dob_pool = [a for a in age_pool if a[2] == "dob"]

        if len(dob_pool) >= 2:
            dob_counter = Counter(a[0] for a in dob_pool)
            best_norm   = dob_counter.most_common(1)[0][0]
            best_entry  = next(a for a in dob_pool if a[0] == best_norm)
            best_age    = best_entry[0]
            age_src     = best_entry[1]
            print(f"    → DOB consensus ({len(dob_pool)} sources): {best_age}")
        else:
            counter     = Counter(a[0] for a in age_pool)
            most_common = counter.most_common()
            if len(most_common) > 1 and most_common[0][1] == most_common[1][1]:
                best_entry = max(age_pool, key=lambda a: a[0])
            else:
                best_norm  = most_common[0][0]
                best_entry = next(a for a in age_pool if a[0] == best_norm)
            best_age = best_entry[3]
            age_src  = best_entry[1]
        print(f"  [Age] Winner: {best_age} | {fmt_source(age_src)} ✓")
    else:
        best_age = None
        age_src  = None
        print(f"  [Age] Not found")

    # ── NATIONALITY ───────────────────────────────────────────────────────────
    print(f"\n  [Nationality] Running frequency vote across all sources...")
    nat_pool = []
    for e in extractions:
        nat = e.get("nationality")
        if nat and str(nat).lower() != "null":
            nat_pool.append((nat, e.get("source", "")))
            print(f"    Found: {nat} | {fmt_source(e.get('source', ''))}")

    if nat_pool:
        counter  = Counter(n[0] for n in nat_pool)
        best_nat = counter.most_common(1)[0][0]
        nat_src  = next(n[1] for n in nat_pool if n[0] == best_nat)
        print(f"  [Nationality] Winner: {best_nat} ({counter.most_common(1)[0][1]} votes) | {fmt_source(nat_src)} ✓")
    else:
        best_nat = None
        nat_src  = None
        print(f"  [Nationality] Not found")

    # ── NET WORTH ─────────────────────────────────────────────────────────────
    print(f"\n  [Net Worth] Finding most recent & credible figure...")
    CREDIBLE_NW = {"forbes.com", "bloomberg.com", "reuters.com", "wsj.com", "ft.com"}

    nw_pool = []
    for e in extractions:
        nw   = e.get("net_worth")
        year = e.get("net_worth_year")
        src  = e.get("source", "")
        if nw and str(nw).lower() != "null" and "null" not in str(nw).lower():
            credible = any(c in src.lower() for c in CREDIBLE_NW)
            nw_pool.append({"nw": nw, "year": year or 0, "source": src, "credible": credible})
            tag = " [CREDIBLE]" if credible else ""
            print(f"    Found: {nw} ({year}){tag} | {fmt_source(src)}")

    if nw_pool:
        credible_pool = [x for x in nw_pool if x["credible"]]
        if credible_pool:
            credible_pool.sort(key=lambda x: x["year"], reverse=True)
            latest_year   = credible_pool[0]["year"]
            latest        = [x for x in credible_pool if x["year"] == latest_year]
            counter       = Counter(x["nw"] for x in latest)
            best_nw_val   = counter.most_common(1)[0][0]
            best_nw_entry = next(x for x in latest if x["nw"] == best_nw_val)
            print(f"    → Using credible source (most recent)")
        else:
            nw_pool.sort(key=lambda x: x["year"], reverse=True)
            latest_year   = nw_pool[0]["year"]
            latest        = [x for x in nw_pool if x["year"] == latest_year]
            counter       = Counter(x["nw"] for x in latest)
            best_nw_val   = counter.most_common(1)[0][0]
            best_nw_entry = next(x for x in latest if x["nw"] == best_nw_val)
            print(f"    → No credible source — using most recent")
        print(f"  [Net Worth] Winner: {best_nw_entry['nw']} ({best_nw_entry['year']}) | {fmt_source(best_nw_entry['source'])} ✓")
        best_nw     = best_nw_entry["nw"]
        latest_year = best_nw_entry["year"]
        best_nw_src = best_nw_entry["source"]
    else:
        best_nw     = None
        latest_year = None
        best_nw_src = None
        print(f"  [Net Worth] Not found")

    # ── EDUCATION ────────────────────────────────────────────────────────────
    print(f"\n  [Education] Grouping degrees by institution...")
    VAGUE_DEGREES = {"undergraduate degree", "architect", "graduate", "degree"}

    edu_pool = []
    for e in extractions:
        deg  = e.get("degree")
        inst = e.get("institution")
        if deg and str(deg).lower() != "null":
            if deg.lower().strip() in VAGUE_DEGREES:
                print(f"    Skipped vague: '{deg}' | {fmt_source(e.get('source', ''))}")
                continue
            if inst and str(inst).lower() != "null":
                edu_pool.append({"degree": deg, "institution": inst, "source": e.get("source", "")})
                print(f"    Found: {deg}, {inst} | {fmt_source(e.get('source', ''))}")
            else:
                print(f"    Skipped (no institution): '{deg}' | {fmt_source(e.get('source', ''))}")

    if edu_pool:
        inst_groups = defaultdict(list)
        for e in edu_pool:
            inst_groups[e["institution"]].append(e)

        merged = []
        for inst, entries in inst_groups.items():
            unique_degrees = list(set(e["degree"] for e in entries))

            if len(entries) >= 2 and len(unique_degrees) > 1:
                # Multiple different degree names for same uni — ask LLM to resolve
                print(f"\n    [Education] Multiple degree names at {inst} — asking LLM to resolve...")
                degrees_list = "\n".join(f"- {d}" for d in unique_degrees)
                prompt = f"""Multiple sources describe {name}'s degree from {inst} differently:
{degrees_list}

Your job is to decide which of these are the same degree described differently, and which are genuinely different degrees.

Rules:
- Degree LEVEL: Bachelor = undergraduate, Master = postgraduate taught, PhD/Doctor = doctoral.
- If two entries are at the SAME level (both Bachelor, both Master, both PhD) and in the SAME or similar field — they are the SAME degree. Return only ONE canonical name for them, the most descriptive and complete version.
- Example: "Bachelor of Science", "Bachelor's degree in Computer Science", "Bachelor of Science Degree in Computer Science with High Distinction" are ALL the same Bachelor's degree — return only "Bachelor of Science in Computer Science".
- Only return MULTIPLE entries if the degrees are at genuinely DIFFERENT levels (e.g. one Bachelor AND one PhD) or in completely different fields.
- Use full formal names only. No abbreviations.
- Return ONLY a JSON array of strings, no explanation, no markdown.

Example of SAME degree: ["Bachelor of Science", "Bachelor of Science in Computer Science"] → ["Bachelor of Science in Computer Science"]
Example of DIFFERENT degrees: ["Bachelor of Science in Computer Science", "Doctor of Philosophy in Computer Science"] → ["Bachelor of Science in Computer Science", "Doctor of Philosophy in Computer Science"]"""

                raw = ask_llm(prompt)
                raw = re.sub(r"```json|```", "", raw).strip()
                try:
                    resolved = json.loads(raw)
                    if not isinstance(resolved, list):
                        resolved = [unique_degrees[0]]
                except Exception:
                    resolved = [unique_degrees[0]]

                # Python post-filter: if LLM still returned same-level dupes, keep most descriptive
                level_map = {}
                for deg in resolved:
                    lvl = degree_level(deg)
                    if lvl not in level_map or len(deg) > len(level_map[lvl]):
                        level_map[lvl] = deg
                resolved = list(level_map.values())

                print(f"    LLM resolved → {resolved}")
                best_src = entries[0]["source"]
                for deg in resolved:
                    merged.append({"degree": deg, "institution": inst, "source": best_src, "votes": len(entries)})

            else:
                # Single degree or unanimous — frequency vote with honours stripping
                deg_counter = Counter(e["degree"] for e in entries)
                normalised  = Counter()
                for deg, cnt in deg_counter.items():
                    normalised[strip_honours(deg)] += cnt
                best_norm = normalised.most_common(1)[0][0]
                best_deg  = next(e["degree"] for e in entries if strip_honours(e["degree"]) == best_norm)
                best_src  = next(e["source"] for e in entries if e["degree"] == best_deg)
                merged.append({"degree": best_deg, "institution": inst, "source": best_src, "votes": len(entries)})

        # Final filter — prefer entries with 2+ votes
        result_degrees = []
        for m in sorted(merged, key=lambda x: x["votes"], reverse=True):
            if m["votes"] >= 2:
                result_degrees.append(m)
                print(f"  [Education] Winner: {m['degree']}, {m['institution']} ({m['votes']} votes) | {fmt_source(m['source'])} ✓")

        if not result_degrees:
            top = sorted(merged, key=lambda x: x["votes"], reverse=True)[0]
            result_degrees.append(top)
            print(f"  [Education] Winner (single source): {top['degree']}, {top['institution']} | {fmt_source(top['source'])} ✓")

        best_edu = result_degrees
    else:
        best_edu = []
        print(f"  [Education] Not found")

    print(f"\n{'='*65}")

    return {
        "age":         best_age,
        "age_year":    CURRENT_YEAR,
        "age_source":  age_src,
        "nationality": best_nat,
        "nat_source":  nat_src,
        "net_worth":   best_nw,
        "nw_year":     latest_year if nw_pool else None,
        "nw_source":   best_nw_src,
        "education":   best_edu,
    }
