"""
build_index.py
--------------
Run this ONCE to scrape all fish slugs and basic metadata from Fishipedia
and save them to fish_index.json. Commit that file to your repo so the
hourly bot never has to crawl the listing pages again.

Usage:
    pip install requests beautifulsoup4
    python build_index.py
"""

import requests
from bs4 import BeautifulSoup
import json
import time

BASE_URL = "https://www.fishi-pedia.com"
LISTING_URL = BASE_URL + "/en/poissons"
TOTAL_PAGES = 48  # Update this if the site grows
OUTPUT_FILE = "fish_index.json"
HEADERS = {"User-Agent": "HourlyFish/1.0 (educational bot; contact: your@email.com)"}


def scrape_page(page_num):
    """Scrape one listing page and return a list of fish dicts."""
    url = LISTING_URL if page_num == 1 else f"{LISTING_URL}?pg={page_num}"
    print(f"  Scraping page {page_num}/{TOTAL_PAGES}: {url}")

    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    fish_list = []

    # Each fish on the listing page has an anchor linking to its detail page.
    # The slug pattern is /fishes/<latin-name>
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "/fishes/" in href and href.startswith(BASE_URL + "/fishes/"):
            slug = href.replace(BASE_URL, "")

            # Skip category pages like /fishes/type/... or /fishes/famille/...
            parts = slug.split("/")
            if len(parts) != 3:
                continue

            # Grab the text inside the link for a rough common name
            text = link.get_text(separator=" ", strip=True)

            # Avoid duplicates (same slug may appear multiple times per page)
            if not any(f["slug"] == slug for f in fish_list):
                fish_list.append({
                    "slug": slug,
                    "label": text[:120] if text else slug.split("/")[-1]
                })

    return fish_list


def main():
    all_fish = []
    seen_slugs = set()

    for page in range(1, TOTAL_PAGES + 1):
        try:
            fish_on_page = scrape_page(page)
            for fish in fish_on_page:
                if fish["slug"] not in seen_slugs:
                    all_fish.append(fish)
                    seen_slugs.add(fish["slug"])
            # Be polite — don't hammer the server
            time.sleep(1.5)
        except Exception as e:
            print(f"  ERROR on page {page}: {e}")
            continue

    print(f"\nTotal fish collected: {len(all_fish)}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_fish, f, ensure_ascii=False, indent=2)

    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
