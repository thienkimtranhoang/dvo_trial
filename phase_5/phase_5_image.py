"""
Phase 5 Image — Find and download a photo of the person using Tavily image search.
Saves as phase_5/photo.jpg — replaced on every run.
"""
import os
import sys
import requests
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import TAVILY_API_KEY

PHOTO_PATH = Path(__file__).parent / "photo.jpg"

SKIP_DOMAINS = {
    "shutterstock.com", "gettyimages.com", "istockphoto.com",
    "alamy.com", "dreamstime.com", "stock.adobe.com",
}


def is_valid_image_url(url: str) -> bool:
    if not url:
        return False
    if any(d in url.lower() for d in SKIP_DOMAINS):
        return False
    if not any(url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
        # Accept URLs without extension too — many valid images don't have extensions
        return True
    return True


def search_and_download(name: str) -> str | None:
    """
    Search Tavily for a photo of the person.
    Downloads first valid image to phase_5/photo.jpg.
    Returns path if successful, None if not found.
    """
    print(f"\n  Searching for photo of {name}...")

    queries = [
        f"{name} photo portrait",
        f"{name} headshot",
        f"{name} profile picture",
    ]

    image_urls = []
    for query in queries:
        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {TAVILY_API_KEY}"},
                json={
                    "query":          query,
                    "include_images": True,
                    "max_results":    5,
                },
                timeout=15,
            )
            resp.raise_for_status()
            images = resp.json().get("images", [])
            for img in images:
                url = img if isinstance(img, str) else img.get("url", "")
                if url and is_valid_image_url(url):
                    image_urls.append(url)
        except Exception as e:
            print(f"    [IMAGE SEARCH ERROR] {query[:40]} → {e}")

        if image_urls:
            break  # stop at first query that returns images

    if not image_urls:
        print(f"  ⚠️  No photo found for {name}")
        return None

    # Try downloading images until one succeeds
    for url in image_urls[:5]:
        try:
            resp = requests.get(url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            resp.raise_for_status()

            # Validate it's actually an image
            content_type = resp.headers.get("content-type", "")
            if "image" not in content_type and len(resp.content) < 1000:
                continue

            PHOTO_PATH.write_bytes(resp.content)
            print(f"  ✅ Photo saved: {PHOTO_PATH} ({len(resp.content)//1024}KB)")
            return str(PHOTO_PATH)

        except Exception as e:
            print(f"    [DOWNLOAD ERROR] {url[:55]} → {e}")
            continue

    print(f"  ⚠️  Could not download any photo for {name}")
    return None
