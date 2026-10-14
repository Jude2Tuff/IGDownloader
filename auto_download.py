"""Automatic Instagram video downloader.

Each run picks random accounts from config.json, scans their recent posts,
and downloads videos that meet the view threshold and haven't been saved yet.
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
LOG_FILE = ROOT / "logs" / "auto_download.log"

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


def find_candidates(loader, username, config, archive):
    profile = instaloader.Profile.from_username(loader.context, username)
    candidates = []
    for post in islice(profile.get_posts(), config["posts_to_scan_per_account"]):
        if not post.is_video or post.shortcode in archive:
            continue
        views = view_count(post)
        if views >= config["min_views"]:
            candidates.append((post, views))
    return candidates


def main():
    parser = argparse.ArgumentParser(description="Automatic Instagram video downloader.")
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
    accounts = random.sample(config["accounts"], min(config["accounts_per_run"], len(config["accounts"])))
    log.info("Run started. Accounts this run: %s", ", ".join(accounts))

    candidates = []
    for username in accounts:
        try:
            found = find_candidates(loader, username, config, archive)
            log.info("@%s: %d new videos with >= %d views", username, len(found), config["min_views"])
            candidates.extend((username, post, views) for post, views in found)
        except Exception as e:
            log.warning("@%s: skipped (%s)", username, e)
        time.sleep(random.uniform(5, 15))  # pause between accounts to look less like a bot

    random.shuffle(candidates)
    downloaded = 0
    for username, post, views in candidates[: config["videos_per_run"]]:
        name = f"{username}_{post.shortcode}"
        if args.dry_run:
            log.info("[dry run] would download %s (%d views)", name, views)
            continue
        try:
            loader.download_pic(str(out_dir / name), post.video_url, post.date_utc)
            add_to_archive(post.shortcode)
            downloaded += 1
            log.info("Downloaded %s (%d views)", name, views)
        except Exception as e:
            log.warning("Failed %s: %s", name, e)
        time.sleep(random.uniform(3, 10))

    log.info("Run finished. %d videos downloaded.", downloaded)
    return 0


if __name__ == "__main__":
    sys.exit(main())
