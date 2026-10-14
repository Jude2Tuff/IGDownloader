# Instagram Video Downloader

Downloads Instagram reels and video posts as MP4 files, using [yt-dlp](https://github.com/yt-dlp/yt-dlp).

Only download videos you own or have permission to save.

## Setup (once on each computer)

```bash
git clone <your-repo-url>
cd TestVideos
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

FFmpeg is optional but recommended. Some videos come as separate video and audio streams, and yt-dlp needs FFmpeg to merge them: `winget install Gyan.FFmpeg`

## Usage

```bash
python ig_download.py https://www.instagram.com/reel/XXXXXXXXX/
python ig_download.py -f urls.txt            # one URL per line
python ig_download.py URL -o my_folder       # choose output folder
python ig_download.py URL --cookies-from-browser edge   # private posts or posts that need a login
```

Videos are saved to `downloads/`. Git ignores that folder, so videos stay on the machine that downloaded them.

If downloads start failing, Instagram has probably changed something. Update yt-dlp with `pip install -U yt-dlp`.

## Automatic mode

`auto_download.py` runs on a schedule. Each run picks random accounts from your list, scans their recent posts, and downloads videos above your view threshold. Videos it has already saved are skipped (tracked in `downloaded.txt`).

1. Edit `config.json`:
   - `instagram_username`: the Instagram account the script logs in as. Use a spare account, because automated scraping can get an account rate-limited or banned.
   - `accounts`: the accounts to pull videos from
   - `runs_per_day`, `accounts_per_run`, `videos_per_run`, `min_views`, `posts_to_scan_per_account`
2. Log in once (you type your password; it's saved as a session file, not in this repo):
   ```bash
   .venv\Scripts\instaloader --login YOUR_LOGIN_USERNAME
   ```
3. Test without downloading: `.venv\Scripts\python auto_download.py --dry-run`
4. Turn on the schedule: `powershell -ExecutionPolicy Bypass -File setup_schedule.ps1`

Logs are in `logs/auto_download.log`. Run the schedule on **one** computer only, because each machine keeps its own download history. To stop it: `Unregister-ScheduledTask -TaskName IGDownloader -Confirm:$false`

## Syncing between computers

```bash
git pull     # before you start working
git add -A
git commit -m "describe change"
git push     # when you're done
```
