# Instagram Downloader

Automatically downloads reels and pictures from a list of Instagram accounts, then lets you swipe through them to keep or delete each one.

Only download content you own or have permission to save.

## Setup (once on each computer)

```bash
git clone https://github.com/Jude2Tuff/IGDownloader.git
cd IGDownloader
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Folders

```
downloads/
  unprocessed/        new videos and images land here, waiting for review
  processed_videos/   videos you kept
  processed_images/   images you kept
```

Each file has a matching `.txt` with its caption. Git ignores `downloads/`, so files stay on the machine that downloaded them.

## Automatic downloads

`auto_download.py` fetches the newest posts of every account in `config.json` through [Apify](https://apify.com/apify/instagram-scraper), with no Instagram login. Results are cached in `cache/` for a day, so only the first run each day uses Apify credit. Each fetch costs about (`max_reels_to_scan_per_account` + `picture_posts_to_consider`) × accounts × $0.0027. The defaults (8 + 5) × 4 = 52 results come to about $0.14 a day, or $4.35 a month, inside the free plan's $5.

- **Reels:** takes each account's newest reels with at least `min_views` (up to `qualifying_reels_per_account` each, looking back at most `max_reels_to_scan_per_account` posts), then downloads `videos_per_run` of them at random, spread across the accounts.
- **Pictures:** no view requirement. From each account's newest `picture_posts_to_consider` posts, downloads `pictures_per_account` at random. Slideshows contribute one random image.

Nothing is downloaded twice (tracked in `downloaded.txt`).

1. Edit `config.json`. Add accounts to `accounts` and adjust the numbers.
2. Apify token: sign up at apify.com, copy your token from Settings > API & Integrations, run `setx APIFY_TOKEN "your-token"` in Command Prompt, then open a new window. Do this on each computer.
3. Test without downloading: `.venv\Scripts\python auto_download.py --dry-run`
4. Turn on the schedule: `powershell -ExecutionPolicy Bypass -File setup_schedule.ps1`

### Posts shared by DM

Each run also checks @lamefinesser's DMs through the Meta app (xxc) and downloads any post that an account in `dm_senders` shared there. These are saved as `dm_<shortcode>` and use yt-dlp with no login and no Apify credit. Needs `setx IG_TOKEN "token"` (from the Meta app dashboard, API setup with Instagram login, Generate token on @lamefinesser's row). The token renews itself about once a week. The Meta app must stay **published**, or DMs stop showing up. Only a chat's 20 newest messages are visible, and captions come through empty.

Use `--only reels`, `--only pictures` or `--only dms` to download just one kind. Logs are in `logs/auto_download.log`. Run the schedule on **one** computer only. To stop it: `Unregister-ScheduledTask -TaskName IGDownloader -Confirm:$false`

## Reviewing

Double-click `review.bat` (or run `.venv\Scripts\python review.py`). It opens in your browser and shows everything in `unprocessed/` one at a time.

- **Green check** / → / Enter / drag right: keep (moves to `processed_videos/` or `processed_images/`)
- **Red X** / ← / X / drag left: delete (sends to the Recycle Bin)
- ↑ ↓ / scroll / drag up or down: move between items without deciding
- M: sound on/off. Tap the caption to expand it. Filter by Reels or Pictures at the top.

Close the black window to stop the review app.

## Manual download

`ig_download.py URL` downloads a single post or reel with yt-dlp.

## Syncing between computers

```bash
git pull     # before you start working
git add -A
git commit -m "describe change"
git push     # when you're done
```
