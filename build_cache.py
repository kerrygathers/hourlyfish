"""
build_cache.py
--------------
Fetches detailed data (title, image, description, IUCN status) for all fish
in fish_index.json and caches it in fish_cache.json.

Run this occasionally to refresh the cache. Commit fish_cache.json to the repo.

Usage:
    python build_cache.py
"""

import json
import time
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.fishi-pedia.com"
INDEX_FILE = "fish_index.json"
CACHE_FILE = "fish_cache.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
    "Referer": "https://www.fishi-pedia.com/",
}

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


def fetch_fish_data(slug):
    """Fetch detailed data for a single fish."""
    url = BASE_URL + slug
    
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            break
        except Exception as e:
            if attempt < 2:
                wait_time = (attempt + 1) * 5
                print(f"  Retry {attempt + 1}/3 after {wait_time}s: {e}")
                time.sleep(wait_time)
            else:
                print(f"  FAILED after 3 attempts: {e}")
                return None
    
    soup = BeautifulSoup(r.text, "html.parser")

    # Extract image URL
    image_url = None
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        image_url = og_image["content"]

    # Extract title
    title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].replace(" • Fish sheet", "").strip()

    # Extract description
    description = ""
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        description = og_desc["content"].strip()
    if not description:
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            description = meta_desc["content"].strip()

    # Extract IUCN status
    iucn_code = ""
    for tag in soup.find_all(class_=lambda c: c and "iucn" in c.lower()):
        text = tag.get_text(strip=True).upper()
        if text in IUCN_LABELS:
            iucn_code = text
            break

    return {
        "slug": slug,
        "title": title,
        "image_url": image_url,
        "description": description,
        "iucn_code": iucn_code,
    }


def main():
    # Load fish index
    with open(INDEX_FILE, encoding="utf-8") as f:
        fish_list = json.load(f)

    print(f"Building cache for {len(fish_list)} fish...")
    cache = {}

    for i, entry in enumerate(fish_list, 1):
        slug = entry["slug"]
        print(f"[{i}/{len(fish_list)}] {slug}...")
        
        data = fetch_fish_data(slug)
        if data:
            cache[slug] = data
            print(f"  ✓ Cached")
        
        # Be polite to the server
        time.sleep(1.5)

    # Save cache
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Cached {len(cache)}/{len(fish_list)} fish to {CACHE_FILE}")
    print("Commit this file to your repo so bot.py can use it.")


if __name__ == "__main__":
    main()
