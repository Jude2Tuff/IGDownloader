"""Swipe-style review of downloaded reels and pictures.

Shows everything in downloads/unprocessed/ one at a time.
  Green check -> moved to downloads/approved_reels/ or downloads/approved_pictures/
  Red X       -> sent to the Recycle Bin

Usage: python review.py   (or double-click review.bat). Opens in your browser.
"""

import json
import shutil
import sys
import threading
import webbrowser
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_from_directory
from send2trash import send2trash

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
DOWNLOADS = ROOT / CONFIG["output_folder"]
UNPROCESSED = DOWNLOADS / "unprocessed"
APPROVED = {"reel": DOWNLOADS / "approved_reels", "picture": DOWNLOADS / "approved_pictures"}
VIDEO_EXT = {".mp4", ".mov", ".webm"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
PORT = 8765

app = Flask(__name__)


def kind_of(path):
    ext = path.suffix.lower()
    return "reel" if ext in VIDEO_EXT else "picture" if ext in IMAGE_EXT else None


def account_of(path):
    # Files are named <account>_<shortcode>; both parts can contain underscores.
    matches = [a for a in CONFIG["accounts"] if path.stem.startswith(a + "_")]
    return max(matches, key=len) if matches else path.stem.rsplit("_", 1)[0]


def unprocessed_file(name):
    path = UNPROCESSED / name
    if Path(name).name != name or not path.is_file() or not kind_of(path):
        abort(404)
    return path


@app.get("/")
def index():
    return send_from_directory(ROOT, "review.html")


@app.get("/api/items")
def items():
    files = sorted((p for p in UNPROCESSED.glob("*") if kind_of(p)), key=lambda p: p.stat().st_mtime)
    result = []
    for p in files:
        caption_file = p.with_suffix(".txt")
        result.append({
            "name": p.name,
            "kind": kind_of(p),
            "account": account_of(p),
            "caption": caption_file.read_text(encoding="utf-8") if caption_file.exists() else "",
        })
    return jsonify(result)


@app.get("/media/<name>")
def media(name):
    unprocessed_file(name)
    return send_from_directory(UNPROCESSED, name, conditional=True)


@app.post("/api/decide")
def decide():
    body = request.get_json()
    path = unprocessed_file(body["name"])
    caption_file = path.with_suffix(".txt")
    if body["action"] == "keep":
        dest = APPROVED[kind_of(path)]
        dest.mkdir(parents=True, exist_ok=True)
        shutil.move(path, dest / path.name)
        if caption_file.exists():
            shutil.move(caption_file, dest / caption_file.name)
    elif body["action"] == "delete":
        send2trash(path)
        if caption_file.exists():
            send2trash(caption_file)
    else:
        abort(400)
    return jsonify(ok=True)


if __name__ == "__main__":
    UNPROCESSED.mkdir(parents=True, exist_ok=True)
    for folder in APPROVED.values():
        folder.mkdir(parents=True, exist_ok=True)
    url = f"http://127.0.0.1:{PORT}"
    print(f"Review app running at {url}  (close this window to stop)")
    if "--no-browser" not in sys.argv:
        threading.Timer(1, webbrowser.open, [url]).start()
    app.run(host="127.0.0.1", port=PORT)
