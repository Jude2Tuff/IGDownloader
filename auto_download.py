"""Automatic Instagram downloader for reels and pictures.

Each run fetches the newest posts of every account in config.json through Apify
(no Instagram login) and saves new items to downloads/unprocessed/ for review
(see review.py):
  - Reels: picks videos_per_run reels at random, spread across the accounts, from
    each account's newest reels that meet min_views.
  - Pictures: from each account's newest picture_posts_to_consider posts, picks
    pictures_per_account at random (one random image from each slideshow).
Each item's caption is saved next to it as a .txt file.
Apify results are cached for a day, so a second run the same day costs nothing.
Needs the APIFY_TOKEN environment variable (apify.com > Settings > API & Integrations).
Meant to be run by Windows Task Scheduler (see setup_schedule.ps1).

Usage:
    python auto_download.py                  # reels and pictures
    python auto_download.py --only pictures  # or --only reels
    python auto_download.py --dry-run        # show what would be downloaded
"""

import argparse
import json
import logging
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yt_dlp

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "config.json"
ARCHIVE_FILE = ROOT / "downloaded.txt"
CACHE_DIR = ROOT / "cache"
LOG_FILE = ROOT / "logs" / "auto_download.log"
CACHE_MAX_AGE = 24 * 60 * 60  # fetch from Apify (and pay) at most once a day
APIFY_URL = "https://api.apify.com/v2/acts/apify~instagram-scraper/run-sync-get-dataset-items"
IG_API = "https://graph.instagram.com/v25.0/"
TOKEN_REFRESHED_FILE = ROOT / "cache" / "ig_token_refreshed"
TOKEN_REFRESH_EVERY = 7 * 24 * 60 * 60  # tokens die after 60 days unless refreshed
SHORTCODE = re.compile(r"instagram\.com/(?:reels?|p|tv)/([\w-]+)")

log = logging.getLogger("ig")


def setup_logging():
    LOG_FILE.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()],
    )


def load_archive():
    if ARCHIVE_FILE.exists():
        return set(ARCHIVE_FILE.read_text(encoding="utf-8").split())
    return set()


def add_to_archive(shortcode):
    with ARCHIVE_FILE.open("a", encoding="utf-8") as f:
        f.write(shortcode + "\n")


def save(out_dir, name, ext, url, post):
    urllib.request.urlretrieve(url, out_dir / f"{name}{ext}")
    (out_dir / f"{name}.txt").write_text(post.get("caption") or "", encoding="utf-8")
    add_to_archive(post["shortCode"])


# ---------- Apify ----------

def apify_items(urls, results_type, limit):
    """Run Apify's Instagram scraper on urls and return its items, or None without a token."""
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        log.error("APIFY_TOKEN isn't set. Copy your token from apify.com > Settings > API & Integrations, "
                  'run: setx APIFY_TOKEN "your-token", then open a new window.')
        return None
    body = json.dumps({"directUrls": urls, "resultsType": results_type, "resultsLimit": limit,
                       "skipPinnedPosts": True}).encode()
    request = urllib.request.Request(APIFY_URL, data=body, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    # ponytail: synchronous call, Apify cuts it off after 5 min; switch to start-run + poll if accounts grow a lot
    with urllib.request.urlopen(request, timeout=330) as response:
        return json.load(response)


def fetch(config, results_type, limit):
    """Return {username: [item, ...]} newest first for results_type ("posts" is the
    main grid, "reels" the reels tab), from today's cache or Apify."""
    cache_file = CACHE_DIR / f"apify_{results_type}.json"
    if cache_file.exists():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if time.time() - cached["fetched_at"] < CACHE_MAX_AGE and cached["accounts"] == config["accounts"]:
            log.info("Using today's cached Apify %s.", results_type)
            return cached["posts"]

    log.info("Fetching %s from Apify...", results_type)
    items = apify_items([f"https://www.instagram.com/{u}/" for u in config["accounts"]], results_type, limit)
    if items is None:
        return None

    posts = {u: [] for u in config["accounts"]}
    for item in items:
        owner = (item.get("ownerUsername") or "").lower()
        if owner in posts and item.get("shortCode"):  # error items (private/missing account) have no shortCode
            posts[owner].append(item)
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file.write_text(json.dumps({"fetched_at": time.time(), "accounts": config["accounts"], "posts": posts}),
                          encoding="utf-8")
    return posts


def view_count(post):
    return max(post.get("videoPlayCount") or 0, post.get("videoViewCount") or 0)


def picture_urls(post):
    """Image URLs for a picture post or slideshow; empty for videos."""
    if post.get("type") == "Sidecar":
        urls = [c.get("displayUrl") for c in post.get("childPosts") or [] if c.get("type") != "Video"]
        urls = urls or post.get("images") or []
    elif post.get("type") == "Image":
        urls = [post.get("displayUrl")]
    else:
        urls = []
    return [u for u in urls if u]


# ---------- Reels ----------

def reel_candidates(posts, config, archive):
    """{shortcode: post} for the newest undownloaded reels that meet min_views."""
    reels = {}
    for post in posts:
        if post.get("type") == "Video" and post.get("videoUrl") and post["shortCode"] not in archive \
                and view_count(post) >= config["min_views"]:
            reels[post["shortCode"]] = post
            if len(reels) >= config["qualifying_reels_per_account"]:
                break
    return reels


def pick_spread(candidates_by_account, count):
    """Pick up to `count` random reels, taking one per account in turn so they're spread out."""
    pools = {user: random.sample(list(reels.items()), len(reels)) for user, reels in candidates_by_account.items()}
    order = list(pools)
    random.shuffle(order)
    picks = []
    while len(picks) < count and any(pools.values()):
        for user in order:
            if pools[user] and len(picks) < count:
                code, post = pools[user].pop()
                picks.append((user, code, post))
    return picks


def download_reels(posts_by_account, config, archive, out_dir, dry_run):
    candidates_by_account = {}
    for username, posts in posts_by_account.items():
        reels = reel_candidates(posts, config, archive)
        log.info("@%s: %d candidate reels with >= %d views", username, len(reels), config["min_views"])
        if reels:
            candidates_by_account[username] = reels

    downloaded = 0
    for username, shortcode, post in pick_spread(candidates_by_account, config["videos_per_run"]):
        name = f"{username}_{shortcode}"
        if dry_run:
            log.info("[dry run] would download reel %s (%d views)", name, view_count(post))
            continue
        try:
            save(out_dir, name, ".mp4", post["videoUrl"], post)
            downloaded += 1
            log.info("Downloaded reel %s (%d views)", name, view_count(post))
        except Exception as e:
            log.warning("Failed reel %s: %s", name, e)
        time.sleep(random.uniform(1, 3))
    return downloaded


# ---------- Pictures ----------

def download_pictures(posts_by_account, config, archive, out_dir, dry_run):
    downloaded = 0
    for username, posts in posts_by_account.items():
        options = [(post, random.choice(urls)) for post in posts[:config["picture_posts_to_consider"]]
                   if post["shortCode"] not in archive and (urls := picture_urls(post))]
        picks = random.sample(options, min(config["pictures_per_account"], len(options)))
        log.info("@%s: %d new picture posts, taking %d", username, len(options), len(picks))
        for post, url in picks:
            name = f"{username}_{post['shortCode']}"
            if dry_run:
                log.info("[dry run] would download picture %s", name)
                continue
            try:
                save(out_dir, name, ".jpg", url, post)
                downloaded += 1
            except Exception as e:
                log.warning("Failed picture %s: %s", name, e)
            time.sleep(random.uniform(1, 3))
    return downloaded


# ---------- Posts shared by DM ----------

def ig_get(path, token, **params):
    url = IG_API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def refresh_token(token):
    """Swap the token for a fresh 60-day one about once a week and save it with setx."""
    if TOKEN_REFRESHED_FILE.exists() and time.time() - TOKEN_REFRESHED_FILE.stat().st_mtime < TOKEN_REFRESH_EVERY:
        return token
    url = "https://graph.instagram.com/refresh_access_token?" + urllib.parse.urlencode(
        {"grant_type": "ig_refresh_token", "access_token": token})
    with urllib.request.urlopen(url, timeout=30) as response:
        token = json.load(response)["access_token"]
    subprocess.run(["setx", "IG_TOKEN", token], check=True, capture_output=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))  # no console pop-up
    TOKEN_REFRESHED_FILE.parent.mkdir(exist_ok=True)
    TOKEN_REFRESHED_FILE.touch()
    log.info("Instagram token refreshed.")
    return token


def shared_links(token, senders):
    """Post links that `senders` shared by DM, from each conversation's newest messages."""
    links = []
    for conv in ig_get("me/conversations", token, platform="instagram", fields="participants")["data"]:
        names = {p.get("username") for p in conv["participants"]["data"]}
        if not names & set(senders):
            continue
        # ponytail: the API only returns a conversation's 20 newest messages; anything older is missed
        messages = ig_get(conv["id"], token, fields="messages{from,message,shares{link}}")["messages"]["data"]
        for message in messages:
            if message.get("from", {}).get("username") in senders:
                links += [s["link"] for s in message.get("shares", {}).get("data", []) if s.get("link")]
                # Shared regular posts arrive empty (Meta only sends them by webhook), so pasted links count too.
                links += ["https://www." + m[0] for m in SHORTCODE.finditer(message.get("message") or "")]
    return links


def download_via_apify(link, name, out_dir):
    """Save every slide of a post (photos and videos) and its caption through Apify, ~$0.003 a post."""
    items = apify_items([link], "posts", 1)
    post = next((i for i in items or [] if i.get("shortCode")), None)
    if not post:
        raise RuntimeError("Apify couldn't find this post")
    slides = [(p["videoUrl"], ".mp4") if p.get("videoUrl") else (p.get("displayUrl"), ".jpg")
              for p in post.get("childPosts") or [post]]
    slides = [(url, ext) for url, ext in slides if url] or [(url, ".jpg") for url in post.get("images") or []]
    if not slides:
        raise RuntimeError("Apify found no media in this post")
    for i, (url, ext) in enumerate(slides, 1):
        file_name = name if len(slides) == 1 else f"{name}_{i}"
        urllib.request.urlretrieve(url, out_dir / f"{file_name}{ext}")
        (out_dir / f"{file_name}.txt").write_text(post.get("caption") or "", encoding="utf-8")
    return len(slides)


def download_shared(config, archive, out_dir, dry_run):
    token = os.environ.get("IG_TOKEN")
    if not token:
        log.error('IG_TOKEN isn\'t set. Generate one in the Meta app dashboard, run: setx IG_TOKEN "token", '
                  "then open a new window.")
        return 0
    token = refresh_token(token)
    downloaded = 0
    for link in shared_links(token, config["dm_senders"]):
        match = SHORTCODE.search(link)
        if not match or match[1] in archive:
            continue
        shortcode = match[1]
        name = f"dm_{shortcode}"
        if dry_run:
            log.info("[dry run] would download shared post %s", link)
            continue
        try:
            if "/reel" in link:  # free; yt-dlp handles single videos
                with yt_dlp.YoutubeDL({"outtmpl": str(out_dir / f"{name}.%(ext)s"), "quiet": True,
                                       "noprogress": True}) as ydl:
                    info = ydl.extract_info(link)
                (out_dir / f"{name}.txt").write_text(info.get("description") or "", encoding="utf-8")
            else:  # photo posts and slideshows: yt-dlp would skip the photos
                log.info("%s: %d slide(s)", link, download_via_apify(link, name, out_dir))
            add_to_archive(shortcode)
            archive.add(shortcode)
            downloaded += 1
            log.info("Downloaded shared post %s", link)
        except Exception as e:
            log.warning("Failed shared post %s: %s", link, e)
    return downloaded


def main():
    parser = argparse.ArgumentParser(description="Automatic Instagram downloader.")
    parser.add_argument("--dry-run", action="store_true", help="list matches without downloading")
    parser.add_argument("--only", choices=["reels", "pictures", "dms"], help="download just one kind")
    args = parser.parse_args()

    setup_logging()
    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    out_dir = ROOT / config["output_folder"] / "unprocessed"
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("Run started. %d accounts.", len(config["accounts"]))
    archive = load_archive()
    reels = pictures = shared = 0
    if args.only in (None, "dms") and config.get("dm_senders"):
        try:
            shared = download_shared(config, archive, out_dir, args.dry_run)
        except Exception as e:
            log.error("Checking DMs failed: %s", e)
    try:
        if args.only in (None, "reels"):
            reels_by_account = fetch(config, "reels", config["max_reels_to_scan_per_account"])
            if reels_by_account is None:
                return 1
            reels = download_reels(reels_by_account, config, archive, out_dir, args.dry_run)
        if args.only in (None, "pictures"):
            posts_by_account = fetch(config, "posts", config["picture_posts_to_consider"])
            if posts_by_account is None:
                return 1
            pictures = download_pictures(posts_by_account, config, archive, out_dir, args.dry_run)
    except Exception as e:
        log.error("Apify request failed: %s", e)
        return 1
    log.info("Run finished. %d reels, %d pictures and %d shared posts downloaded.", reels, pictures, shared)
    return 0


if __name__ == "__main__":
    sys.exit(main())
