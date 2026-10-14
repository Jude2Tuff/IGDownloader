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

## Syncing between computers

```bash
git pull     # before you start working
git add -A
git commit -m "describe change"
git push     # when you're done
```
