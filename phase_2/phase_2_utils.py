import re
import json
import time
import datetime
import requests

# ── CONFIG ────────────────────────────────────────────────────────────────────
TINYFISH_API_KEY = "your_tinyfish_api_key_here"
TAVILY_API_KEY   = "your_tavily_api_key_here"
OLLAMA_URL       = "http://localhost:11434/api/chat"
OLLAMA_MODEL     = "qwen2.5:7b"
CURRENT_YEAR     = datetime.date.today().year

BAD_SOURCES = {
    "facebook.com", "wordpress.com", "blogspot.com", "reddit.com",
    "quora.com", "instagram.com", "twitter.com", "tiktok.com",
    "x.com", "linkedin.com", "gurufocus.com", "macrotrends.net",
    "youtube.com", "wikipedia.org/wiki/List",
    "nas.gov.sg", "fastpeoplesearch.com", "commonwealthofworldchinatowns.com", "wenxuecity.com",
}

USELESS_CONTENT = [
    "javascript is disabled", "verify you are human",
    "enable javascript", "blocked by cloudflare",
    "status': 'failed", "status': 'blocked",
]


# ── HELPERS ───────────────────────────────────────────────────────────────────

def is_bad_source(url: str) -> bool:
    return any(b in url.lower() for b in BAD_SOURCES)


def is_useless(text: str) -> bool:
    return not text or len(text) < 200 or any(u in text.lower() for u in USELESS_CONTENT)


def parse_json(raw: str):
    raw = re.sub(r"```json|```", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        try:
            return json.loads(m.group()) if m else {}
        except Exception:
            return {}


def fmt_source(url: str) -> str:
    if not url:
        return ""
    try:
        return url.split("/")[2]
    except Exception:
        return url[:50]


def strip_honours(d: str) -> str:
    return d.lower().replace("(honours)", "").replace("(hons)", "").strip()


def ask_llm(prompt: str) -> str:
    for attempt in range(3):
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "format": "json",
                    "stream": False,
                },
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
        except Exception:
            if attempt == 2:
                return ""
            time.sleep(3)
    return ""
