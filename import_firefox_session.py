"""Copy your Instagram login from Firefox into instaloader, so auto_download.py
can use it without logging in itself (avoids Instagram's "Checkpoint required").

1. Sign in to instagram.com in Firefox.
2. Run: python import_firefox_session.py
Rerun whenever Instagram signs that session out.
"""

import json
import shutil
import sqlite3
import sys
import tempfile
from glob import glob
from os.path import expandvars, getmtime
from pathlib import Path

import instaloader

CONFIG_FILE = Path(__file__).resolve().parent / "config.json"


def find_cookie_file():
    files = glob(expandvars(r"%APPDATA%\Mozilla\Firefox\Profiles\*\cookies.sqlite"))
    if not files:
        sys.exit("No Firefox profile found. Open Firefox once and sign in to instagram.com.")
    return max(files, key=getmtime)  # most recently used profile


def read_instagram_cookies(cookie_file):
    # Firefox locks the database while running, so read a copy.
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "cookies.sqlite"
        shutil.copy(cookie_file, copy)
        conn = sqlite3.connect(copy)
        rows = conn.execute("SELECT name, value FROM moz_cookies WHERE host LIKE '%instagram.com'").fetchall()
        conn.close()
    return dict(rows)


def main():
    cookies = read_instagram_cookies(find_cookie_file())
    if "sessionid" not in cookies:
        sys.exit("Firefox isn't signed in to Instagram. Sign in at instagram.com in Firefox, then rerun.")

    loader = instaloader.Instaloader(max_connection_attempts=1)
    loader.context._session.cookies.update(cookies)
    username = loader.test_login()
    if not username:
        sys.exit("Instagram rejected the Firefox session. Sign out and back in to Instagram in Firefox, then rerun.")

    loader.context.username = username
    loader.save_session_to_file()

    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    config["instagram_username"] = username
    CONFIG_FILE.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"Imported Firefox login for @{username} and saved it to config.json.")


if __name__ == "__main__":
    main()
