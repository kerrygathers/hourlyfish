"""
bot.py
------
Run hourly (via GitHub Actions cron) to post one fish to Bluesky.
Reads the next fish from fish_index.json, looks up cached data from fish_cache.json,
downloads its image, and posts with a caption to Bluesky.

Required environment variables (set as GitHub Secrets):
    BSKY_HANDLE   — e.g. yourbot.bsky.social
    BSKY_PASSWORD — an App Password from Bluesky settings (not your real password)

Dependencies:
    pip install requests beautifulsoup4 atproto python-dotenv

Note: Run build_cache.py occasionally to refresh fish_cache.json with the latest
data from fishi-pedia.com.
"""

import os
import json
import time
import requests
from atproto import Client, models

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_URL = "https://www.fishi-pedia.com"
INDEX_FILE = "fish_index.json"
CACHE_FILE = "fish_cache.json"
COUNTER_FILE = "counter.txt"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.fishi-pedia.com/",
}

# IUCN status codes → readable labels for the post caption
IUCN_LABELS = {
    "LC": "Least Concern ✅",
    "NT": "Near Threatened 🟡",
    "VU": "Vulnerable 🟠",
    "EN": "Endangered 🔴",
    "CR": "Critically Endangered 🚨",
    "EW": "Extinct in the Wild ⬛",
    "EX": "Extinct ⬛",
    "DD": "Data Deficient ❓",
}

# Create a persistent session for image downloads
session = requests.Session()


def load_index():
    with open(INDEX_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_cache():
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"⚠ {CACHE_FILE} not found. Run build_cache.py first.")
        return {}


def get_counter(total):
    """Read counter, return current index, and write incremented value."""
    if os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE) as f:
            idx = int(f.read().strip())
    else:
        idx = 0
    next_idx = (idx + 1) % total
    with open(COUNTER_FILE, "w") as f:
        f.write(str(next_idx))
    return idx


def download_image(image_url):
    """Download image bytes from the provided URL."""
    for attempt in range(4):
        try:
            print(f"Downloading image (attempt {attempt + 1}/4)...")
            r = session.get(image_url, headers=HEADERS, timeout=25)
            r.raise_for_status()
            print("✓ Image downloaded successfully")
            return r.content
        except Exception as e:
            if attempt < 3:
                wait_time = (attempt + 1) * 3
                print(f"Download failed: {e}, retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise
    raise RuntimeError(f"Failed to download image after 4 attempts: {image_url}")


def build_post_text(fish):
    """Build the Bluesky post caption (max 300 chars)."""
    lines = []

    if fish.get("title"):
        lines.append(fish["title"])

    if fish.get("iucn_code"):
        label = IUCN_LABELS.get(fish["iucn_code"], fish["iucn_code"])
        lines.append(f"Conservation status: {label}")

    if fish.get("description"):
        # Trim description to leave room for URL
        max_desc = 200 - len(fish["slug"]) - 30
        desc = fish["description"]
        if len(desc) > max_desc:
            desc = desc[:max_desc].rsplit(" ", 1)[0] + "…"
        lines.append(desc)

    url = BASE_URL + fish["slug"]
    lines.append(f"🔗 {url}")
    lines.append("#fish")

    text = "\n\n".join(lines)

    # Bluesky hard limit: 300 graphemes
    if len(text) > 300:
        text = text[:297] + "…"

    return text


def post_to_bluesky(fish, img_bytes):
    """Upload image and post to Bluesky."""
    handle = os.environ["BSKY_HANDLE"]
    password = os.environ["BSKY_PASSWORD"]

    client = Client()
    client.login(handle, password)

    # Upload the blob
    upload = client.upload_blob(img_bytes)

    # Build post text and alt text
    text = build_post_text(fish)
    alt_text = fish.get("title") or "Fish"

    # Create the image embed
    image_embed = models.AppBskyEmbedImages.Main(
        images=[
            models.AppBskyEmbedImages.Image(
                alt=alt_text,
                image=upload.blob,
            )
        ]
    )

    # Send the post
    client.send_post(text=text, embed=image_embed)
    print(f"✓ Posted: {fish.get('title', fish['slug'])} — {BASE_URL + fish['slug']}")


def main():
    # Load fish index and cache
    fish_list = load_index()
    if not fish_list:
        raise RuntimeError(f"{INDEX_FILE} is empty. Run build_index.py first.")

    cache = load_cache()
    if not cache:
        raise RuntimeError(f"{CACHE_FILE} is empty. Run build_cache.py first.")

    # Get the current fish to post
    idx = get_counter(len(fish_list))
    entry = fish_list[idx]
    slug = entry["slug"]
    print(f"Posting fish #{idx}: {slug}")

    # Look up fish data in cache
    if slug not in cache:
        raise RuntimeError(f"Fish {slug} not in cache. Run build_cache.py to update.")

    fish = cache[slug]

    if not fish.get("image_url"):
        print("⚠ No image found — skipping this fish.")
        return

    # Download and post
    img_bytes = download_image(fish["image_url"])
    post_to_bluesky(fish, img_bytes)


if __name__ == "__main__":
    main()
