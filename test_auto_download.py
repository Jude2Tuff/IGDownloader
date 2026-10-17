"""Offline check of the picking logic (no Apify calls). Run: python test_auto_download.py"""
from auto_download import SHORTCODE, pick_spread, picture_urls, reel_candidates

assert SHORTCODE.search("https://www.instagram.com/reel/DaoA6notjvT/")[1] == "DaoA6notjvT"
assert SHORTCODE.search("https://www.instagram.com/p/Ab-c_1/?igsh=x")[1] == "Ab-c_1"
assert SHORTCODE.search("https://www.instagram.com/lamefinesser/") is None

config = {"min_views": 100, "qualifying_reels_per_account": 2}
posts = [
    {"shortCode": "a", "type": "Video", "videoUrl": "v", "videoPlayCount": 500},
    {"shortCode": "b", "type": "Video", "videoUrl": "v", "videoViewCount": 50},   # too few views
    {"shortCode": "c", "type": "Video", "videoUrl": "v", "videoPlayCount": 900},  # already downloaded
    {"shortCode": "d", "type": "Image", "displayUrl": "img"},
    {"shortCode": "e", "type": "Video", "videoUrl": "v", "videoPlayCount": 200},
    {"shortCode": "f", "type": "Video", "videoUrl": "v", "videoPlayCount": 300},  # past the per-account cap
]
assert list(reel_candidates(posts, config, archive={"c"})) == ["a", "e"]

assert picture_urls(posts[0]) == []
assert picture_urls(posts[3]) == ["img"]
sidecar = {"type": "Sidecar", "childPosts": [{"type": "Image", "displayUrl": "1"}, {"type": "Video", "displayUrl": "2"}]}
assert picture_urls(sidecar) == ["1"]
assert picture_urls({"type": "Sidecar", "childPosts": [], "images": ["x"]}) == ["x"]

picks = pick_spread({"u1": {"a": {}, "b": {}, "c": {}}, "u2": {"d": {}}}, 3)
assert len(picks) == 3 and {p[0] for p in picks} == {"u1", "u2"}
from pathlib import Path
from upload import post_of
assert post_of(Path("dm_DeaFWqjoPpn_3.jpg")) == ("dm_DeaFWqjoPpn", 3)
assert post_of(Path("criingemoist_DefugT_PfQO.jpg")) == ("criingemoist_DefugT_PfQO", 0)  # underscore in shortcode
print("ok")
