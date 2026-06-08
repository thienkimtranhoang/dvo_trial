import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env.local from project root
env_path = Path(__file__).parent / ".env.local"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()  # fallback to system env

# ── API KEYS ──────────────────────────────────────────────────────────────────
TINYFISH_API_KEY = os.getenv("TINYFISH_API_KEY", "")
TAVILY_API_KEY   = os.getenv("TAVILY_API_KEY", "")
SERP_API_KEY     = os.getenv("SERP_API_KEY", "")

# ── LOCAL LLM ─────────────────────────────────────────────────────────────────
OLLAMA_URL   = os.getenv("OLLAMA_URL",   "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

# ── PATHS ─────────────────────────────────────────────────────────────────────
ROOT_DIR     = Path(__file__).parent
OUTPUTS_DIR  = ROOT_DIR / "outputs"
TEMPLATE_PATH = ROOT_DIR / "phase_6" / "template" / "Individual Template.docx"

# ── PHASE 2 ATTRIBUTES ────────────────────────────────────────────────────────
ATTRIBUTES = [
    "BIOGRAPHY",
    "FAMILY",
    "INTERESTING_FACTS",
    "ADVERSE_NEWS",
    "GIVING",
    "POTENTIAL_CONNECTORS",
]

def validate():
    missing = []
    if not TINYFISH_API_KEY: missing.append("TINYFISH_API_KEY")
    if not TAVILY_API_KEY:   missing.append("TAVILY_API_KEY")
    if missing:
        print(f"⚠️  Missing keys in .env.local: {', '.join(missing)}")
        print(f"   Copy .env.example to .env.local and fill in your keys.")
        return False
    return True

# ── ORG ATTRIBUTE KEYWORDS ───────────────────────────────────────────────────
ORG_ATTRIBUTE_KEYWORDS = {
    "DATE_OF_ESTABLISHMENT":  ["founded", "established", "incorporated", "since", "history"],
    "BIOGRAPHY":              ["company", "organisation", "headquartered", "operates", "mission", "overview", "profile"],
    "GIVING":       ["donation", "donated", "scholarship", "bursary", "CSR", "charity", "philanthropy", "grant", "programme", "foundation", "community investment"],
    "DEMONSTRATED_INTERESTS": ["interest", "focus", "commitment", "initiative", "programme", "annual", "champions", "cause"],
    "OTHER_INTERESTING_FACTS":["achievement", "award", "milestone", "acquisition", "record", "first", "recognised", "consecutive"],
    "POTENTIAL_CONNECTORS":   ["partnership", "partner", "board", "executive", "founder", "chairman", "director", "collaborat"],
    "ADVERSE_NEWS":           ["controversy", "lawsuit", "scandal", "investigation", "criticism", "regulatory", "violation", "complaint"],
}

# ── PHASE 2 BAD SOURCES ───────────────────────────────────────────────────────
BAD_SOURCES = {
    "facebook.com", "instagram.com", "twitter.com", "tiktok.com",
    "x.com", "reddit.com", "quora.com", "blogspot.com",
    "linkedin.com", "nationalgeographic.com", "nhm.ac.uk",
    "kids.nationalgeographic.com", "wikipedia.org/wiki/List",
}

# ── PHASE 2 ATTRIBUTE KEYWORDS ────────────────────────────────────────────────
ATTRIBUTE_KEYWORDS = {
    "BIOGRAPHY":            ["born in", "biography", "early life", "grew up", "founded", "started his career", "began his career", "his story", "personal history"],
    "FAMILY":               ["his wife", "her husband", "his children", "his son", "his daughter", "married to", "his spouse", "his parents", "his siblings"],
    "INTERESTING_FACTS":    ["hobby", "hobbies", "passionate about", "in his spare time", "he enjoys", "outdoor activities", "personal interest", "known for his"],
    "ADVERSE_NEWS":         ["controversy", "lawsuit", "sued", "scandal", "fraud", "investigation", "criticism", "accused", "fined", "penalty", "alleged", "scrutiny", "complaint", "environmental", "pollution", "community", "violated", "illegal", "corruption", "bribery", "sanction"],
    "GIVING":               ["donated", "philanthropy", "charity", "CSR", "scholarship", "foundation", "social responsibility", "community project", "humanitarian"],
    "POTENTIAL_CONNECTORS": ["co-investor", "consortium", "joint venture", "co-founder", "strategic partner", "business ally", "collaborated with", "partnered with"],
    "DEMONSTRATED_INTERESTS": ["hobby", "hobbies", "walking", "gobi", "macritchie", "passionate about", "enjoys", "personal interest", "team building"],
    "GIVING2": ["scholarship", "bursary", "donation", "hospital", "school", "solar panel", "dental", "vaccination", "foundation", "CSR"],

}

# ── PHASE 2 SEARCH QUERIES ────────────────────────────────────────────────────
def build_queries(name: str, company: str = None) -> list:
    c = f" {company}" if company else ""
    return [
        ("BIOGRAPHY",              f"{name}{c} biography background career history"),
        ("FAMILY",                 f"{name}{c} family wife husband children parents siblings personal"),
        ("INTERESTING_FACTS",      f"{name}{c} award honor achievement record title milestone"),
        ("DEMONSTRATED_INTERESTS", f"{name}{c} hobby interest passion personal activity lifestyle"),
        ("ADVERSE_NEWS",           f"{name}{c} controversy lawsuit scandal criticism investigation"),
        ("GIVING",                 f"{name}{c} philanthropy donation scholarship CSR charity community"),
        ("GIVING2",                f"{name}{c} foundation hospital school bursary social responsibility"),
        ("POTENTIAL_CONNECTORS",   f"{name}{c} partners associates board investors joint venture"),
    ]
