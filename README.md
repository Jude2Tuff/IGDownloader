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
  unprocessed/        new downloads land here, waiting for review
  approved_reels/     reels you kept
  approved_pictures/  pictures you kept
```

Each file has a matching `.txt` with its caption. Git ignores `downloads/`, so files stay on the machine that downloaded them.

## Automatic downloads

`auto_download.py` scans every account in `config.json` on each run:

- **Reels:** takes each account's newest reels with at least `min_views` (up to `qualifying_reels_per_account` each, looking back at most `max_reels_to_scan_per_account`), then downloads `videos_per_run` of them at random, spread across the accounts. Reel scans are cached in `cache/` for a day.
- **Pictures:** no view requirement. From each account's newest `picture_posts_to_consider` posts, downloads `pictures_per_account` at random. Slideshows contribute one random image.

Nothing is downloaded twice (tracked in `downloaded.txt`).

1. Edit `config.json`. Add accounts to `accounts` and adjust the numbers.
2. Log in: sign in to instagram.com in **Firefox** (use a spare account; automated scraping can get an account rate-limited or banned), then run `.venv\Scripts\python import_firefox_session.py`. It copies that login (no password needed). Rerun it if Instagram ever signs you out.
3. Test without downloading: `.venv\Scripts\python auto_download.py --dry-run`
4. Turn on the schedule: `powershell -ExecutionPolicy Bypass -File setup_schedule.ps1`

Use `--only reels` or `--only pictures` to download just one kind. Logs are in `logs/auto_download.log`. Run the schedule on **one** computer only. To stop it: `Unregister-ScheduledTask -TaskName IGDownloader -Confirm:$false`

## Reviewing

Double-click `review.bat` (or run `.venv\Scripts\python review.py`). It opens in your browser and shows everything in `unprocessed/` one at a time.

- **Green check** / → / Enter / drag right: keep (moves to the approved folder)
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
