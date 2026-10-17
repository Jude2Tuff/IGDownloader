"""Post approved downloads to Instagram (the account IG_TOKEN belongs to).

Usage:
    python upload.py reel              # oldest captioned video in processed_videos/
    python upload.py post              # oldest captioned image or slideshow in processed_images/
    python upload.py reel --dry-run    # show what would be posted

Captions come from the .txt next to each file; files without one are skipped.
Slides of one post (name_1.jpg, name_2.jpg, ...) post together as a slideshow.
With tracks in music/ a slideshow becomes a video with a random track, posted
as a reel; otherwise it posts as a swipeable carousel.
Instagram only takes media from a public link, so each file is hosted on
litterbox.catbox.moe for an hour. Posted files move to downloads/posted/.
"""

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from auto_download import CONFIG_FILE, IG_API, ROOT, ig_get, log, refresh_token, setup_logging

CONFIG = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
DOWNLOADS = ROOT / CONFIG["output_folder"]
VIDEOS = DOWNLOADS / "processed_videos"
IMAGES = DOWNLOADS / "processed_images"
POSTED = DOWNLOADS / "posted"
MUSIC = ROOT / "music"
VIDEO_EXT = {".mp4", ".mov"}
IMAGE_EXT = {".jpg", ".jpeg", ".png"}
AUDIO_EXT = {".mp3", ".m4a", ".wav"}
LITTERBOX = "https://litterbox.catbox.moe/resources/internals/api.php"
SLIDE_SECONDS = 3
MAX_SLIDES = 10  # Instagram's carousel limit
SLIDESHOW_CHANCE = 0.7  # how often a loose image gets bundled into a slideshow instead of posting alone
CAPTION_LIMIT = 2200  # Instagram's maximum
SLIDE = re.compile(r"^(.*)_(\d+)$")


def caption_of(path):
    txt = path.with_suffix(".txt")
    return txt.read_text(encoding="utf-8").strip()[:CAPTION_LIMIT] if txt.exists() else ""


def random_caption():
    """An AI caption from any downloaded post, for media that came without one."""
    texts = [t for t in (p.read_text(encoding="utf-8").strip() for p in DOWNLOADS.rglob("*.txt")) if t]
    return random.choice(texts)[:CAPTION_LIMIT] if texts else ""


def queue(folder, extensions):
    """Media in folder, oldest first."""
    return sorted((p for p in folder.glob("*") if p.suffix.lower() in extensions), key=lambda p: p.stat().st_mtime)


def post_of(path):
    """('dm_ABC', 2) for dm_ABC_2.jpg; single images are their own post with slide 0."""
    match = SLIDE.match(path.stem)
    return (match[1], int(match[2])) if match else (path.stem, 0)


def pick_post():
    """The oldest captioned image, with the rest of its slides in order."""
    images = queue(IMAGES, IMAGE_EXT)
    if not images:
        return None, []
    name = post_of(images[0])[0]
    slides = sorted((p for p in images if post_of(p)[0] == name), key=lambda p: post_of(p)[1])[:MAX_SLIDES]
    if len(slides) == 1 and random.random() < SLIDESHOW_CHANCE:  # bundle loose images into a slideshow
        singles = [p for p in images if post_of(p)[1] == 0][:random.randint(3, 5)]
        if len(singles) > 1:
            slides = singles
    return ("slideshow" if len(slides) > 1 else "image"), slides


# ---------- Hosting and Instagram ----------

def host(path):
    """Upload to litterbox for an hour and return the public link."""
    boundary = uuid.uuid4().hex
    fields = b"".join(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        for name, value in (("reqtype", "fileupload"), ("time", "1h")))
    file_head = (f'--{boundary}\r\nContent-Disposition: form-data; name="fileToUpload"; filename="{path.name}"\r\n'
                 f"Content-Type: application/octet-stream\r\n\r\n").encode()
    body = fields + file_head + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(LITTERBOX, data=body, headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": "IGDownloader"})
    with urllib.request.urlopen(request, timeout=300) as response:
        url = response.read().decode().strip()
    if not url.startswith("https://"):
        raise RuntimeError(f"Hosting failed: {url}")
    return url


def ig_post(path, token, **params):
    request = urllib.request.Request(IG_API + path, data=urllib.parse.urlencode(params).encode(),
                                     headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Instagram refused it: {e.read().decode()[:300]}") from None


def container(user_id, token, **params):
    """Create a media container and wait until Instagram has processed it."""
    creation_id = ig_post(f"{user_id}/media", token, **params)["id"]
    for _ in range(60):
        status = ig_get(creation_id, token, fields="status_code")["status_code"]
        if status == "FINISHED":
            return creation_id
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram couldn't process the media ({status})")
        time.sleep(10)
    raise RuntimeError("Instagram took over 10 minutes to process the media")


def publish(user_id, token, creation_id):
    media_id = ig_post(f"{user_id}/media_publish", token, creation_id=creation_id)["id"]
    return ig_get(media_id, token, fields="permalink").get("permalink", media_id)


def slideshow_video(images, track, out_path):
    """Render images (SLIDE_SECONDS each, 1080x1920) over a music track with FFmpeg."""
    total = SLIDE_SECONDS * len(images)
    command = ["ffmpeg", "-y", "-loglevel", "error"]
    for image in images:
        command += ["-loop", "1", "-t", str(SLIDE_SECONDS), "-i", str(image)]
    command += ["-i", str(track)]
    scaled = "".join(
        f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
        f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{i}];" for i in range(len(images)))
    joined = "".join(f"[v{i}]" for i in range(len(images))) + f"concat=n={len(images)}:v=1:a=0[v];"
    fade = f"[{len(images)}:a]afade=t=out:st={total - 1}:d=1[a]"
    command += ["-filter_complex", scaled + joined + fade, "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                "-t", str(total), "-movflags", "+faststart", str(out_path)]
    subprocess.run(command, check=True)


# ---------- Main ----------

def move_to_posted(paths):
    POSTED.mkdir(parents=True, exist_ok=True)
    for path in paths:
        for f in (path, path.with_suffix(".txt")):
            if f.exists():
                shutil.move(f, POSTED / f.name)


def main():
    parser = argparse.ArgumentParser(description="Post approved downloads to Instagram.")
    parser.add_argument("kind", choices=["reel", "post"])
    parser.add_argument("--dry-run", action="store_true", help="show what would be posted")
    args = parser.parse_args()
    setup_logging()

    if args.kind == "reel":
        videos = queue(VIDEOS, VIDEO_EXT)
        kind, files = ("reel", videos[:1]) if videos else (None, [])
    else:
        kind, files = pick_post()
    if not files:
        log.info("Nothing to post for %s: the queue is empty.", args.kind)
        return 0
    caption = caption_of(files[0])
    if not caption:
        caption = random_caption()
        log.info("No caption saved, using a random one.")
    tracks = [p for p in MUSIC.glob("*") if p.suffix.lower() in AUDIO_EXT] if MUSIC.exists() else []
    log.info("Posting %s: %s", kind, ", ".join(p.name for p in files))
    if args.dry_run:
        if kind != "reel":
            log.info("[dry run] as %s", "a reel with music" if tracks else "a plain image/carousel (music/ is empty)")
        log.info("[dry run] caption: %s", caption[:120].replace("\n", " "))
        return 0

    token = refresh_token(os.environ["IG_TOKEN"])
    user_id = ig_get("me", token, fields="user_id")["user_id"]
    try:
        if kind == "reel":
            creation = container(user_id, token, media_type="REELS", video_url=host(files[0]), caption=caption)
        elif tracks:  # images and slideshows go out as reels set to music
            with tempfile.TemporaryDirectory() as tmp:
                video = Path(tmp) / "slideshow.mp4"
                slideshow_video(files, random.choice(tracks), video)
                creation = container(user_id, token, media_type="REELS", video_url=host(video), caption=caption)
        elif kind == "image":
            creation = container(user_id, token, image_url=host(files[0]), caption=caption)
        else:
            children = [container(user_id, token, image_url=host(p), is_carousel_item="true") for p in files]
            creation = container(user_id, token, media_type="CAROUSEL", children=",".join(children), caption=caption)
        link = publish(user_id, token, creation)
    except Exception as e:
        log.error("Posting %s failed: %s", kind, e)
        return 1
    move_to_posted(files)
    log.info("Posted %s: %s", kind, link)
    return 0


if __name__ == "__main__":
    sys.exit(main())
