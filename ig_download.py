"""Download Instagram videos (reels, posts, IGTV) with yt-dlp.

Usage:
    python ig_download.py URL [URL ...]
    python ig_download.py -f urls.txt
    python ig_download.py URL --cookies-from-browser chrome   # for login-only posts
"""

import argparse
import sys
from pathlib import Path

from yt_dlp import YoutubeDL


def read_urls(args):
    urls = list(args.urls)
    if args.file:
        for line in Path(args.file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


def main():
    parser = argparse.ArgumentParser(description="Download Instagram videos.")
    parser.add_argument("urls", nargs="*", help="Instagram post/reel URLs")
    parser.add_argument("-f", "--file", help="text file with one URL per line")
    parser.add_argument("-o", "--output", default="downloads", help="output folder (default: downloads)")
    parser.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        help="use your logged-in browser session (chrome, edge, firefox) for posts that need login",
    )
    args = parser.parse_args()

    urls = read_urls(args)
    if not urls:
        parser.error("give at least one URL or use -f urls.txt")

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    options = {
        "outtmpl": str(out_dir / "%(uploader)s_%(id)s.%(ext)s"),
        "format": "bestvideo*+bestaudio/best",
        "merge_output_format": "mp4",
        "ignoreerrors": True,
    }
    if args.cookies_from_browser:
        options["cookiesfrombrowser"] = (args.cookies_from_browser,)

    with YoutubeDL(options) as ydl:
        failed = ydl.download(urls)

    print(f"\nDone. Files saved to: {out_dir.resolve()}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
