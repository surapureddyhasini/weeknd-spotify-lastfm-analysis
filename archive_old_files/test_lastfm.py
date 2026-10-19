import os, requests
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv("LASTFM_API_KEY")

def try_query(artist, track, autocorrect):
    r = requests.get("https://ws.audioscrobbler.com/2.0/", params={
        "method": "track.getInfo", "artist": artist, "track": track,
        "api_key": api_key, "format": "json", "autocorrect": autocorrect,
    }, timeout=15)
    d = r.json()
    if "error" in d:
        return f"ERROR {d['error']}: {d.get('message')}"
    t = d.get("track", {})
    return f"OK -> {t.get('name')} by {t.get('artist',{}).get('name')} | playcount={t.get('playcount')}"

candidates = [
    ("The Weeknd", "I Was Never There", 1),
    ("The Weeknd", "I Was Never There", 0),
    ("The Weeknd", "I Was Never There (feat. Gesaffelstein)", 1),
    ("The Weeknd", "Reflections Laughing", 1),
    ("The Weeknd", "Reflections Laughing", 0),
    ("The Weeknd", "Reflections Laughing (feat. Travis Scott, Florence + The Machine)", 0),
]
for a, t, ac in candidates:
    print(f"{a} | {t} | autocorrect={ac} -> {try_query(a, t, ac)}")