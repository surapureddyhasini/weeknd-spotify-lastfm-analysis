"""Fetch ISRCs for the audited catalogue, without rebuilding anything else.

Adds a `isrc` column to weeknd_tracks_audited_final.csv and writes
weeknd_tracks_audited_final_with_isrc.csv. Your original file is preserved.
"""
import json, os, time
from pathlib import Path
import pandas as pd
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv

load_dotenv()
sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=os.getenv("SPOTIFY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
))

df = pd.read_csv("weeknd_tracks_audited_final.csv")
track_ids = df["track_id"].dropna().astype(str).unique().tolist()

cache_path = Path("weeknd_isrc_cache.json")
cache: dict[str, str] = {}
if cache_path.exists():
    try:
        cache = json.loads(cache_path.read_text())
    except json.JSONDecodeError:
        cache = {}

fetched = 0
blocked = False
for i, tid in enumerate(track_ids, 1):
    if tid in cache:
        continue
    try:
        t = sp.track(tid)
        isrc = (t.get("external_ids") or {}).get("isrc", "") or ""
        cache[tid] = isrc
        fetched += 1
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        print(f"  {tid}: {exc}")
        if status == 403:
            blocked = True
            break
    if i % 25 == 0:
        print(f"  {i}/{len(track_ids)} (fetched so far: {fetched})")
    time.sleep(0.1)

cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True))
print(f"Cache now holds {len(cache)} entries.")

df["isrc"] = df["track_id"].astype(str).map(cache).fillna("")
df.to_csv("weeknd_tracks_audited_final_with_isrc.csv", index=False)

n_with_isrc = (df["isrc"].fillna("") != "").sum()
print(f"Rows with ISRC: {n_with_isrc}/{len(df)}")
if blocked:
    print("Hit 403 again — Spotify still blocking. Continuing without full ISRCs.")