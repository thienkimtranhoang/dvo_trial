import re
import time
import requests
import concurrent.futures
from config import OLLAMA_URL, OLLAMA_MODEL, ATTRIBUTES


def ask_llm(prompt: str) -> str:
    for attempt in range(3):
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={
                    "model":    OLLAMA_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream":   False,
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


def merge_attribute(attr: str, chunks: list[dict], name: str) -> dict:
    if not chunks:
        return {"attribute": attr, "content": None, "sources": []}

    # Build numbered source list
    sources = []
    seen    = set()
    for c in chunks:
        url = c["source_url"]
        if url not in seen:
            seen.add(url)
            sources.append(url)

    sources_text = ""
    for i, c in enumerate(chunks, 1):
        src_num = sources.index(c["source_url"]) + 1
        sources_text += f"\nSource [{src_num}] ({c['source_url']}):\n{c['text']}\n"

    source_list = "\n".join(f"[{i+1}] {url}" for i, url in enumerate(sources))

    prompt = f"""You are writing the {attr} section about {name} for a professional profile document.

Below are content pieces from different sources:
{sources_text}

Source reference list:
{source_list}

Instructions:
- Write a single cohesive paragraph (not bullet points) about {name}'s {attr.lower().replace('_', ' ')}.
- Merge and deduplicate all facts — do not repeat the same information.
- After each fact or sentence, add an inline citation like [[1]] or [[2]] referring to the source number.
- Only include information explicitly about {name}.
- Keep it factual, professional, and concise.
- Do NOT add information not present in the sources.
- Return only the paragraph text with inline citations, no headers, no extra text.

Example format:
{name} founded the company in 2002 [[1]]. He later expanded into mining operations in Guinea [[2]], forming key partnerships with major Chinese firms [[1]].
"""

    content = ask_llm(prompt)
    print(f"    ✅ {attr:<25} merged ({len(chunks)} sources)")

    return {
        "attribute": attr,
        "content":   content,
        "sources":   sources,
    }


def run(attribute_buckets: dict, name: str) -> dict:
    print(f"\n  Running {len(attribute_buckets)} parallel LLM merge calls...")

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        futures = {
            executor.submit(merge_attribute, attr, chunks, name): attr
            for attr, chunks in attribute_buckets.items()
        }
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results[result["attribute"]] = result

    for attr in ATTRIBUTES:
        if attr not in results:
            results[attr] = {"attribute": attr, "content": None, "sources": []}

    return results
