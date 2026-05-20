# ── API KEYS ──────────────────────────────────────────────────────────────────
TINYFISH_API_KEY = "your_tinyfish_api_key_here"
TAVILY_API_KEY   = "your_tavily_api_key_here"
OLLAMA_URL       = "http://localhost:11434/api/chat"
OLLAMA_MODEL     = "qwen2.5:7b"

# ── DEEP ATTRIBUTES ───────────────────────────────────────────────────────────
ATTRIBUTES = [
    "BIOGRAPHY",
    "FAMILY",
    "INTERESTING_FACTS",
    "ADVERSE_NEWS",
    "GIVING",
    "POTENTIAL_CONNECTORS",
    "KEY_POSITIONS",
]

# ── ATTRIBUTE KEYWORDS ────────────────────────────────────────────────────────
ATTRIBUTE_KEYWORDS = {
    "BIOGRAPHY":            ["born in", "biography", "early life", "grew up", "founded", "started his career", "began his career", "his story", "personal history"],
    "FAMILY":               ["his wife", "her husband", "his children", "his son", "his daughter", "married to", "his spouse", "his parents", "his siblings"],
    "INTERESTING_FACTS":    ["hobby", "hobbies", "passionate about", "in his spare time", "he enjoys", "he walks", "outdoor activities", "personal interest", "known for his"],
    "ADVERSE_NEWS":         ["controversy", "lawsuit", "sued", "scandal", "fraud", "investigation", "criticism", "accused", "fined", "penalty", "alleged", "scrutiny", "complaint"],
    "GIVING":               ["donated", "philanthropy", "charity", "CSR", "scholarship", "foundation", "social responsibility", "community project", "humanitarian"],
    "POTENTIAL_CONNECTORS": ["co-investor", "consortium", "joint venture", "co-founder", "strategic partner", "business ally", "collaborated with", "partnered with"],
    "KEY_POSITIONS":        ["CEO", "chairman", "president", "managing director", "appointed as", "serves as", "head of", "chief executive", "founded and leads"],
}

# ── BAD SOURCES ───────────────────────────────────────────────────────────────
BAD_SOURCES = {
    "facebook.com", "instagram.com", "twitter.com", "tiktok.com",
    "x.com", "reddit.com", "quora.com", "blogspot.com",
    "linkedin.com", "nationalgeographic.com", "nhm.ac.uk",
    "kids.nationalgeographic.com", "wikipedia.org/wiki/List",
}

# ── SEARCH QUERIES PER ATTRIBUTE ─────────────────────────────────────────────
def build_queries(name: str, company: str = None) -> list[tuple]:
    c = f" {company}" if company else ""
    return [
        ("BIOGRAPHY",            f"{name}{c} biography background career history"),
        ("FAMILY",               f"{name}{c} family wife children personal life"),
        ("INTERESTING_FACTS",    f"{name}{c} interests hobbies personal facts"),
        ("ADVERSE_NEWS",         f"{name}{c} controversy lawsuit scandal criticism"),
        ("GIVING",               f"{name}{c} philanthropy donation charity CSR"),
        ("POTENTIAL_CONNECTORS", f"{name}{c} partners associates board directors"),
        ("KEY_POSITIONS",        f"{name}{c} CEO chairman position role organization"),
    ]
