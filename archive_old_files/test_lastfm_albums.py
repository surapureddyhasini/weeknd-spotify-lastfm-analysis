import os

import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("LASTFM_API_KEY")
BASE = "https://ws.audioscrobbler.com/2.0/"


def lastfm(method, **params):
    params.update({"method": method, "api_key": api_key, "format": "json"})
    r = requests.get(BASE, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


# 1. Top albums
print("TOP ALBUMS")
albums = lastfm("artist.getTopAlbums", artist="The Weeknd", limit=10)
for a in albums["topalbums"]["album"]:
    print(f"{a['name']} | Playcount: {a['playcount']}")

# 2. Album info (listeners + playcount + track list)
print("\nALBUM INFO: After Hours")
info = lastfm("album.getInfo", artist="The Weeknd", album="After Hours")
alb = info["album"]
print(f"Listeners: {alb.get('listeners')} | Playcount: {alb.get('playcount')}")
tracks = alb.get("tracks", {}).get("track", [])
print("Tracks returned:", len(tracks))

# 3. Track info
print("\nTRACK INFO: Blinding Lights")
t = lastfm("track.getInfo", artist="The Weeknd", track="Blinding Lights")
print(
    f"Listeners: {t['track'].get('listeners')} | "
    f"Playcount: {t['track'].get('playcount')}"
)