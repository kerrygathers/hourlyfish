"""
bot.py
------
Run hourly (via GitHub Actions cron) to post one fish to Bluesky.
Reads the next fish from fish_index.json, fetches its detail page,
downloads its image, and posts with a caption to Bluesky.

Required environment variables (set as GitHub Secrets):
    BSKY_HANDLE   — e.g. yourbot.bsky.social
    BSKY_PASSWORD — an App Password from Bluesky settings (not your real password)

Dependencies:
    pip install requests beautifulsoup4 atproto python-dotenv
"""

import os
import json
import time
import requests
from bs4 import BeautifulSoup
from atproto import Client, models

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_URL = "https://www.fishi-pedia.com"
INDEX_FILE = "fish_index.json"
COUNTER_FILE = "counter.txt"
HEADERS = {"User-Agent": "HourlyFish/1.0 (educational bot; contact: kerry.gathers@proton.me)"}

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


def load_index():
    with open(INDEX_FILE, encoding="utf-8") as f:
        return json.load(f)


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


def fetch_fish_data(slug):
    """Fetch a fish detail page and extract image URL, name, description, and metadata."""
    url = BASE_URL + slug
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # Image: og:image is the most reliable source — it's in the HTML head
    image_url = None
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        image_url = og_image["content"]

    # Title: "Common name • Latin name • Fish sheet"
    raw_title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        raw_title = og_title["content"].replace(" • Fish sheet", "").strip()

    # Description: og:description or meta description
    description = ""
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        description = og_desc["content"].strip()
    if not description:
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            description = meta_desc["content"].strip()

    # IUCN status: look for a short badge text on the page
    iucn_code = ""
    for tag in soup.find_all(class_=lambda c: c and "iucn" in c.lower()):
        text = tag.get_text(strip=True).upper()
        if text in IUCN_LABELS:
            iucn_code = text
            break

    return {
        "url": url,
        "slug": slug,
        "title": raw_title,
        "image_url": image_url,
        "description": description,
        "iucn_code": iucn_code,
    }


def download_image(image_url):
    """Download image bytes, with a retry."""
    for attempt in range(3):
        try:
            r = requests.get(image_url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            return r.content
        except Exception as e:
            print(f"Image download attempt {attempt + 1} failed: {e}")
            time.sleep(2)
    raise RuntimeError(f"Failed to download image after 3 attempts: {image_url}")


def build_post_text(fish):
    """Build the Bluesky post caption (max 300 chars)."""
    lines = []

    if fish["title"]:
        lines.append(fish["title"])

    if fish["iucn_code"]:
        label = IUCN_LABELS.get(fish["iucn_code"], fish["iucn_code"])
        lines.append(f"Conservation status: {label}")

    if fish["description"]:
        # Trim description to leave room for URL
        max_desc = 200 - len(fish["url"]) - 30
        desc = fish["description"]
        if len(desc) > max_desc:
            desc = desc[:max_desc].rsplit(" ", 1)[0] + "…"
        lines.append(desc)

    lines.append(f"🔗 {fish['url']}")
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
    alt_text = fish["title"] or "Fish"

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
    print(f"Posted: {fish['title']} — {fish['url']}")


def main():
    fish_list = load_index()
    if not fish_list:
        raise RuntimeError(f"{INDEX_FILE} is empty. Run build_index.py first.")

    idx = get_counter(len(fish_list))
    entry = fish_list[idx]
    print(f"Posting fish #{idx}: {entry['slug']}")

    fish = fetch_fish_data(entry["slug"])

    if not fish["image_url"]:
        print("No image found — skipping this fish.")
        return

    img_bytes = download_image(fish["image_url"])
    post_to_bluesky(fish, img_bytes)


if __name__ == "__main__":
    main()
