"""Automatic Instagram reel downloader.

Each run picks random accounts from config.json and downloads reels (of any
age) that meet the view threshold and haven't been saved yet. Each account's
full reel list is scanned at most once per day and cached in cache/, so
repeated runs don't hammer Instagram.
Meant to be run by Windows Task Scheduler (see setup_schedule.ps1).

Usage:
    python auto_download.py            # normal run
    python auto_download.py --dry-run  # show what would be downloaded
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


def get_candidates(loader, username, config, archive):
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


def main():
    parser = argparse.ArgumentParser(description="Automatic Instagram reel downloader.")
    parser.add_argument("--dry-run", action="store_true", help="list matches without downloading")
    args = parser.parse_args()

    setup_logging()
    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    out_dir = ROOT / config["output_folder"]
    out_dir.mkdir(parents=True, exist_ok=True)

    loader = instaloader.Instaloader(quiet=True, download_video_thumbnails=False, save_metadata=False)
    try:
        loader.load_session_from_file(config["instagram_username"])
    except FileNotFoundError:
        log.error("No saved login for %s. Run: .venv\\Scripts\\instaloader --login %s",
                  config["instagram_username"], config["instagram_username"])
        return 1

    archive = load_archive()
    accounts = config["accounts"]
    log.info("Run started. Scanning %d accounts.", len(accounts))

    candidates_by_account = {}
    for username in accounts:
        try:
            reels = get_candidates(loader, username, config, archive)
            log.info("@%s: %d candidate reels with >= %d views", username, len(reels), config["min_views"])
            if reels:
                candidates_by_account[username] = reels
        except Exception as e:
            log.warning("@%s: skipped (%s)", username, e)
        time.sleep(random.uniform(5, 15))  # pause between accounts to look less like a bot

    downloaded = 0
    for username, shortcode, views in pick_spread(candidates_by_account, config["videos_per_run"]):
        name = f"{username}_{shortcode}"
        if args.dry_run:
            log.info("[dry run] would download %s (%d views)", name, views)
            continue
        try:
            post = instaloader.Post.from_shortcode(loader.context, shortcode)
            loader.download_pic(str(out_dir / name), post.video_url, post.date_utc)
            (out_dir / f"{name}.txt").write_text(post.caption or "", encoding="utf-8")
            add_to_archive(shortcode)
            downloaded += 1
            log.info("Downloaded %s (%d views)", name, views)
        except Exception as e:
            log.warning("Failed %s: %s", name, e)
        time.sleep(random.uniform(3, 10))

    log.info("Run finished. %d videos downloaded.", downloaded)
    return 0


if __name__ == "__main__":
    sys.exit(main())
