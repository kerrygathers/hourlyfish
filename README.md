# 🐟 HourlyFish

A Bluesky bot that posts a fish from [Fishipedia](https://www.fishi-pedia.com) every hour.

---

## Setup

### 1. Clone this repo and install dependencies

```bash
pip install requests beautifulsoup4 atproto
```

### 2. Build the fish index (run once)

```bash
python build_index.py
```

This scrapes all ~2,400 fish slugs from Fishipedia and saves them to `fish_index.json`.
Commit this file — the bot reads from it without hitting the listing pages again.

```bash
git add fish_index.json
git commit -m "Add fish index"
git push
```

### 3. Create a Bluesky App Password

1. Log in to [bsky.app](https://bsky.app)
2. Go to **Settings → App Passwords → Add App Password**
3. Name it `hourlyfish` and copy the password

### 4. Add GitHub Secrets

In your GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**

| Secret name    | Value                          |
|----------------|--------------------------------|
| `BSKY_HANDLE`  | `yourbot.bsky.social`          |
| `BSKY_PASSWORD`| The App Password from step 3   |

### 5. Add the workflow file

Place `post_fish.yml` in your repo at:

```
.github/workflows/post_fish.yml
```

Then push. GitHub Actions will run the bot at the top of every hour.

---

## File overview

| File               | Purpose                                              |
|--------------------|------------------------------------------------------|
| `build_index.py`   | One-time scraper — builds `fish_index.json`          |
| `fish_index.json`  | All fish slugs (committed to repo, never re-scraped) |
| `bot.py`           | Hourly script — fetches fish data, posts to Bluesky  |
| `counter.txt`      | Tracks which fish to post next (auto-committed)      |
| `.github/workflows/post_fish.yml` | GitHub Actions cron schedule        |

---

## Testing locally

```bash
BSKY_HANDLE=yourbot.bsky.social BSKY_PASSWORD=your-app-password python bot.py
```

---

## Notes

- The bot commits `counter.txt` back to the repo after each run to track state across stateless GitHub Actions runners.
- `[skip ci]` in the commit message prevents the counter commit from triggering another workflow run.
- With ~2,400 fish and hourly posts, the index lasts ~100 days before cycling. After that it wraps around automatically.
- Please credit Fishipedia clearly in your bot's profile and consider reaching out to them for permission.
