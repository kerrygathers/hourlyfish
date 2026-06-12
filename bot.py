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

# Create a persistent session with retries
session = requests.Session()
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

retry_strategy = Retry(
    total=5,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "HEAD"]
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)


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
    
    # Retry with increasing delays to handle rate limiting and 403 errors
    max_retries = 4
    for attempt in range(max_retries):
        try:
            print(f"Fetching {url} (attempt {attempt + 1}/{max_retries})...")
            r = session.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            print("✓ Successfully fetched page")
            break
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 15  # 15s, 30s, 45s, 60s
                    print(f"Got 403 Forbidden, waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                else:
                    print(f"Failed with 403 after {max_retries} attempts")
                    raise
            else:
                raise
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 10
                print(f"Request failed: {e}, waiting {wait_time}s before retry...")
                time.sleep(wait_time)
            else:
                raise
    
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
    for attempt in range(4):
        try:
            print(f"Downloading image (attempt {attempt + 1}/4)...")
            r = session.get(image_url, headers=HEADERS, timeout=25)
            r.raise_for_status()
            print("✓ Image downloaded successfully")
            return r.content
        except Exception as e:
            if attempt < 3:
                wait_time = (attempt + 1) * 5
                print(f"Image download failed: {e}, waiting {wait_time}s before retry...")
                time.sleep(wait_time)
            else:
                raise
    raise RuntimeError(f"Failed to download image after 4 attempts: {image_url}")


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
    print(f"✓ Posted: {fish['title']} — {fish['url']}")


def main():
    fish_list = load_index()
    if not fish_list:
        raise RuntimeError(f"{INDEX_FILE} is empty. Run build_index.py first.")

    idx = get_counter(len(fish_list))
    entry = fish_list[idx]
    print(f"Posting fish #{idx}: {entry['slug']}")

    fish = fetch_fish_data(entry["slug"])

    if not fish["image_url"]:
        print("⚠ No image found — skipping this fish.")
        return

    img_bytes = download_image(fish["image_url"])
    post_to_bluesky(fish, img_bytes)


if __name__ == "__main__":
    main()
