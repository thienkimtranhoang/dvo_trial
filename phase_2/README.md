# Phases 2, 3, 4 — Deep Attribute Extraction Pipeline

## What It Does
Takes a person's name and company, then finds and extracts 7 deep attributes:
- **Biography**
- **Family**
- **Interesting Facts**
- **Adverse News**
- **Giving** (philanthropy/CSR)
- **Potential Connectors** (business partners, associates)
- **Key Positions** (roles and organisations)

---

## File Structure

```
phase_2/
├── phase_2.py            ← START HERE — runs Phase 2 and auto-chains to Phase 3
├── phase_2_search.py     ← fires 7 parallel Tavily searches, one per attribute
├── phase_2_classify.py   ← builds URL → attributes map from snippets
├── phase_2_rank.py       ← ranks URLs by coverage, returns top 20
└── config.py             ← API keys, attribute list, keyword mappings

phase_3/
├── phase_3.py            ← runs Phase 3 and auto-chains to Phase 4
├── phase_3_agent.py      ← fires 20 parallel TinyFish Agent calls
├── phase_3_collect.py    ← groups extracted content by attribute
└── config.py             ← TinyFish and Tavily API keys

phase_4/
├── phase_4.py            ← runs Phase 4 and displays final results
├── phase_4_merge.py      ← 7 parallel LLM calls, one per attribute
└── config.py             ← Ollama URL and model name
```

---

## Before Running — Set Your API Keys

**`phase_2/config.py`**
```python
TAVILY_API_KEY   = "your_tavily_key_here"
TINYFISH_API_KEY = "your_tinyfish_key_here"
```

**`phase_3/config.py`**
```python
TINYFISH_API_KEY = "your_tinyfish_key_here"
TAVILY_API_KEY   = "your_tavily_key_here"
```

Phase 4 uses the local Ollama LLM — no API key needed.

---

## How It Works

**Phase 2 — URL Collection & Classification** (`phase_2/`)

Tavily fires 7 parallel advanced searches — one per attribute. From each result, Tavily returns URLs and content snippets. A URL → attributes map is built immediately from the results using keyword matching. URLs are ranked by how many attributes they cover, with a maximum of 2 URLs per domain to avoid repetition. The top 20 unique URLs are selected, with the top 5 guaranteed to cover all 7 attributes at least twice.

**Phase 3 — Parallel Scraping & Classified Extraction** (`phase_3/`)

20 TinyFish Agent calls fire simultaneously — one per URL. Each agent receives the URL and a prompt scoped strictly to the attributes that URL was tagged for. The agent uses a real browser with stealth mode, reads the full page content, and returns a classified JSON with only the relevant attribute fields filled. All results are then grouped into per-attribute buckets.

**Phase 4 — LLM Merging per Attribute** (`phase_4/`)

7 parallel LLM calls fire — one per attribute. Each call receives all content chunks for that attribute from multiple sources and merges them into a single clean paragraph. Duplicate facts are removed. Each sentence in the output includes an inline citation `[[1]]` referencing the source. A numbered source list is shown at the end of each section.

---

## How To Run

**Prerequisites**
- Ollama installed and running with `qwen2.5:7b` pulled
- Python packages: `requests`
- Phase 2, 3, and 4 folders placed at the same level

**Set the name at the top of `phase_2/phase_2.py`:**
```python
NAME    = "Sun Xiushun"
COMPANY = "Winning International Group"  # set to None if not available
```

**Run — everything chains automatically:**
```bash
cd phase_2
python phase_2.py
```

Phase 2 finishes → automatically calls Phase 3 → automatically calls Phase 4 → displays final results.

Or pass name and company as arguments:
```bash
python phase_2.py "Chen Tianqiao" "Shanda Group"
```

---

## Expected Output

```
═══════════════════════════════════════════════════════════════
  FINAL RESULTS: Chen Tianqiao
═══════════════════════════════════════════════════════════════

  BIOGRAPHY
  ─────────────────────────────────────────────────────────────
  Chen Tianqiao was born on May 16, 1973, in Zhejiang, China [[1]].
  He earned an economics degree from Fudan University in 1993 and
  co-founded Shanda Interactive Entertainment in 1999 [[2]].

  [1] https://www.forbes.com/...
  [2] https://en.wikipedia.org/...

  ADVERSE_NEWS
  ─────────────────────────────────────────────────────────────
  MiroMind faced scrutiny after key scientist Dai Jifeng departed,
  claiming the company attempted to force relocation overseas [[1]].

  [1] https://www.straitstimes.com/...
```

---



