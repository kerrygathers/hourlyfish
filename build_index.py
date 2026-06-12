"""
build_index.py
--------------
Scrape all fish slugs from Fishipedia and save to fish_index.json.

Run this to get the complete fish list before running build_cache.py.

Usage:
    pip install requests beautifulsoup4
    python build_index.py
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import re

BASE_URL = "https://www.fishi-pedia.com"
LISTING_URL = BASE_URL + "/en/poissons"
OUTPUT_FILE = "fish_index.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def scrape_page(page_num):
    """Scrape one listing page and return a list of fish dicts."""
    url = LISTING_URL if page_num == 1 else f"{LISTING_URL}?pg={page_num}"
    print(f"  Page {page_num}: {url}")

    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"    ERROR: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    fish_list = []

    # Look for fish detail page links in the page
    # Try multiple selectors to find fish cards/links
    
    # Common patterns: href="/fishes/LATIN-NAME"
    links = soup.find_all("a", href=re.compile(r"^/fishes/[a-z\-]+$"))
    
    print(f"    Found {len(links)} potential fish links")

    seen = set()
    for link in links:
        href = link.get("href", "").strip()
        
        # Extract just the slug
        if href.startswith("/fishes/") and "-" in href:
            slug = href
            
            # Get the display text
            text = link.get_text(strip=True)
            
            if slug not in seen and text:
                seen.add(slug)
                fish_list.append({
                    "slug": slug,
                    "label": text[:120]
                })

    print(f"    Added {len(fish_list)} unique fish")
    return fish_list


def main():
    print("Scraping all fish from Fishipedia...")
    print(f"Target: {LISTING_URL}\n")

    all_fish = []
    seen_slugs = set()
    page = 1
    consecutive_empty = 0

    # Try pages until we hit 3 consecutive empty pages
    while consecutive_empty < 3:
        fish_on_page = scrape_page(page)
        
        if not fish_on_page:
            consecutive_empty += 1
            print(f"  (empty page #{consecutive_empty})\n")
        else:
            consecutive_empty = 0
            for fish in fish_on_page:
                if fish["slug"] not in seen_slugs:
                    all_fish.append(fish)
                    seen_slugs.add(fish["slug"])
        
        page += 1
        time.sleep(1)  # Be polite

    print(f"\n{'='*60}")
    print(f"Total fish scraped: {len(all_fish)}")
    print(f"{'='*60}\n")

    if len(all_fish) == 0:
        print("ERROR: No fish found! The site structure may have changed.")
        print("Check that:")
        print("  1. The listing URL is correct")
        print("  2. The site isn't blocking scrapers")
        print("  3. The HTML selectors still match")
        return

    # Save to file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_fish, f, ensure_ascii=False, indent=2)

    print(f"✓ Saved {len(all_fish)} fish to {OUTPUT_FILE}")
    print(f"\nNext: Run 'python build_cache.py' to fetch detailed data")


if __name__ == "__main__":
    main()
