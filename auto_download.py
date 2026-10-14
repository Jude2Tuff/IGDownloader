"""Automatic Instagram downloader for reels and pictures.

Each run scans every account in config.json and saves new items to
downloads/unprocessed/ for review (see review.py):
  - Reels: picks videos_per_run reels at random, spread across the accounts, from
    each account's newest reels that meet min_views. Reel scans are cached for a day.
  - Pictures: from each account's newest picture_posts_to_consider posts, picks
    pictures_per_account at random (one random image from each slideshow).
Each item's caption is saved next to it as a .txt file.
Meant to be run by Windows Task Scheduler (see setup_schedule.ps1).

Usage:
    python auto_download.py                  # reels and pictures
    python auto_download.py --only pictures  # or --only reels
    python auto_download.py --dry-run        # show what would be downloaded
"""

import argparse
import json
import logging
import random
import sys
import time
from itertools import islice
from pathlib import Path

import instaloader

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "config.json"
ARCHIVE_FILE = ROOT / "downloaded.txt"
CACHE_DIR = ROOT / "cache"
LOG_FILE = ROOT / "logs" / "auto_download.log"
CACHE_MAX_AGE = 24 * 60 * 60  # rescan an account's reels once a day

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


def view_count(post):
    counts = [c for c in (post.video_play_count, post.video_view_count) if c is not None]
    return max(counts) if counts else 0


def save(loader, out_dir, name, url, post):
    loader.download_pic(str(out_dir / name), url, post.date_utc)
    (out_dir / f"{name}.txt").write_text(post.caption or "", encoding="utf-8")
    add_to_archive(post.shortcode)


# ---------- Reels ----------

def get_reel_candidates(loader, username, config, archive):
    """Return {shortcode: views} for the account's newest undownloaded reels that
    meet min_views, up to qualifying_reels_per_account. Uses today's cache if fresh."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{username}.json"
    if cache_file.exists():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if time.time() - cached["scanned_at"] < CACHE_MAX_AGE:
            return {code: views for code, views in cached["reels"].items() if code not in archive}

    log.info("@%s: scanning reels...", username)
    profile = instaloader.Profile.from_username(loader.context, username)
    reels = {}
    for post in islice(profile.get_reels(), config["max_reels_to_scan_per_account"]):
        views = view_count(post)
        if views >= config["min_views"] and post.shortcode not in archive:
            reels[post.shortcode] = views
            if len(reels) >= config["qualifying_reels_per_account"]:
                break
    cache_file.write_text(json.dumps({"scanned_at": time.time(), "reels": reels}), encoding="utf-8")
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
                code, views = pools[user].pop()
                picks.append((user, code, views))
    return picks


def download_reels(loader, config, archive, out_dir, dry_run):
    candidates_by_account = {}
    for username in config["accounts"]:
        try:
            reels = get_reel_candidates(loader, username, config, archive)
            log.info("@%s: %d candidate reels with >= %d views", username, len(reels), config["min_views"])
            if reels:
                candidates_by_account[username] = reels
        except Exception as e:
            log.warning("@%s: reels skipped (%s)", username, e)
        time.sleep(random.uniform(5, 15))  # pause between accounts to look less like a bot

    downloaded = 0
    for username, shortcode, views in pick_spread(candidates_by_account, config["videos_per_run"]):
        name = f"{username}_{shortcode}"
        if dry_run:
            log.info("[dry run] would download reel %s (%d views)", name, views)
            continue
        try:
            post = instaloader.Post.from_shortcode(loader.context, shortcode)
            save(loader, out_dir, name, post.video_url, post)
            downloaded += 1
            log.info("Downloaded reel %s (%d views)", name, views)
        except Exception as e:
            log.warning("Failed reel %s: %s", name, e)
        time.sleep(random.uniform(3, 10))
    return downloaded


# ---------- Pictures ----------

def get_picture_options(loader, username, config, archive):
    """Return [(post, image_url)] for undownloaded picture posts among the account's
    newest posts. Slideshows contribute one random image."""
    profile = instaloader.Profile.from_username(loader.context, username)
    options = []
    for post in islice(profile.get_posts(), config["picture_posts_to_consider"]):
        if post.shortcode in archive:
            continue
        if post.typename == "GraphSidecar":
            urls = [node.display_url for node in post.get_sidecar_nodes() if not node.is_video]
        elif not post.is_video:
            urls = [post.url]
        else:
            continue
        if urls:
            options.append((post, random.choice(urls)))
    return options


def download_pictures(loader, config, archive, out_dir, dry_run):
    downloaded = 0
    for username in config["accounts"]:
        try:
            options = get_picture_options(loader, username, config, archive)
        except Exception as e:
            log.warning("@%s: pictures skipped (%s)", username, e)
            continue
        picks = random.sample(options, min(config["pictures_per_account"], len(options)))
        log.info("@%s: %d new picture posts, taking %d", username, len(options), len(picks))
        for post, url in picks:
            name = f"{username}_{post.shortcode}"
            if dry_run:
                log.info("[dry run] would download picture %s", name)
                continue
            try:
                save(loader, out_dir, name, url, post)
                downloaded += 1
            except Exception as e:
                log.warning("Failed picture %s: %s", name, e)
            time.sleep(random.uniform(1, 4))
        time.sleep(random.uniform(5, 15))
    return downloaded


def main():
    parser = argparse.ArgumentParser(description="Automatic Instagram downloader.")
    parser.add_argument("--dry-run", action="store_true", help="list matches without downloading")
    parser.add_argument("--only", choices=["reels", "pictures"], help="download just one kind")
    args = parser.parse_args()

    setup_logging()
    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    out_dir = ROOT / config["output_folder"] / "unprocessed"
    out_dir.mkdir(parents=True, exist_ok=True)

    loader = instaloader.Instaloader(quiet=True, download_video_thumbnails=False, save_metadata=False)
    try:
        loader.load_session_from_file(config["instagram_username"])
    except FileNotFoundError:
        log.error("No saved login for %s. Sign in to Instagram in Firefox, then run import_firefox_session.py",
                  config["instagram_username"])
        return 1

    archive = load_archive()
    log.info("Run started. %d accounts.", len(config["accounts"]))
    reels = pictures = 0
    if args.only != "pictures":
        reels = download_reels(loader, config, archive, out_dir, args.dry_run)
    if args.only != "reels":
        pictures = download_pictures(loader, config, archive, out_dir, args.dry_run)
    log.info("Run finished. %d reels and %d pictures downloaded.", reels, pictures)
    return 0


if __name__ == "__main__":
    sys.exit(main())
