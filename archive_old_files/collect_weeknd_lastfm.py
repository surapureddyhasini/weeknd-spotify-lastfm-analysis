"""Collect Last.fm global track and album statistics for The Weeknd project.

Inputs (same folder):
  - weeknd_tracks_audited_final.csv
  - .env containing LASTFM_API_KEY=your_key

Outputs:
  - weeknd_lastfm_track_stats.csv   one row per Spotify track appearance
  - weeknd_lastfm_album_stats.csv  one row per unique release title queried
  - weeknd_lastfm_collection_log.csv  API misses/errors for manual review

Run: python collect_weeknd_lastfm.py
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

BASE_URL = "https://ws.audioscrobbler.com/2.0/"
INPUT = Path("weeknd_tracks_audited_final.csv")
TRACK_OUT = Path("weeknd_lastfm_track_stats.csv")
ALBUM_OUT = Path("weeknd_lastfm_album_stats.csv")
LOG_OUT = Path("weeknd_lastfm_collection_log.csv")
PAUSE_SECONDS = 0.25


def clean_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def call_lastfm(session: requests.Session, api_key: str, method: str, **params: Any) -> dict:
    payload = {
        "method": method,
        "api_key": api_key,
        "format": "json",
        **params,
    }
    response = session.get(BASE_URL, params=payload, timeout=25)
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise RuntimeError(f"Last.fm error {data.get('error')}: {data.get('message', '')}")
    return data


def main() -> None:
    load_dotenv()
    api_key = os.getenv("LASTFM_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "LASTFM_API_KEY is missing. Add it to a .env file in this folder; "
            "do not paste the key into chat."
        )
    if not INPUT.exists():
        raise SystemExit(f"Cannot find {INPUT.resolve()}. Put this script beside the final CSV.")

    df = pd.read_csv(INPUT)
    required = {"track", "album", "artists", "track_id", "in_default_view", "duration_ms"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"Input CSV is missing required columns: {', '.join(missing)}")

    # Query the global Last.fm track entry using The Weeknd as the primary artist.
    # Cache identical title queries so duplicate release appearances don't cause repeated calls.
    titles = sorted({clean_text(x) for x in df["track"] if clean_text(x)})
    track_cache: dict[str, dict[str, Any]] = {}
    log_rows: list[dict[str, Any]] = []

    with requests.Session() as session:
        for i, title in enumerate(titles, start=1):
            try:
                data = call_lastfm(
                    session, api_key, "track.getInfo", artist="The Weeknd", track=title, autocorrect=1
                )
                t = data.get("track", {})
                track_cache[title] = {
                    "lastfm_track_name": t.get("name"),
                    "lastfm_track_mbid": t.get("mbid"),
                    "lastfm_track_url": t.get("url"),
                    "lastfm_track_listeners": t.get("listeners"),
                    "lastfm_track_playcount": t.get("playcount"),
                    "lastfm_track_match_status": "matched" if t else "empty_response",
                }
            except Exception as exc:
                track_cache[title] = {
                    "lastfm_track_name": None,
                    "lastfm_track_mbid": None,
                    "lastfm_track_url": None,
                    "lastfm_track_listeners": None,
                    "lastfm_track_playcount": None,
                    "lastfm_track_match_status": "error_or_not_found",
                }
                log_rows.append({"kind": "track", "query": title, "error": str(exc)})
            if i % 25 == 0 or i == len(titles):
                print(f"Track lookups: {i}/{len(titles)}")
            time.sleep(PAUSE_SECONDS)

        # Album-level stats are useful for album popularity comparisons. Track-level
        # playcounts should be used for total minutes listened calculations.
        album_names = sorted({clean_text(x) for x in df["album"] if clean_text(x)})
        album_rows: list[dict[str, Any]] = []
        for i, album_name in enumerate(album_names, start=1):
            row: dict[str, Any] = {
                "spotify_release_name": album_name,
                "lastfm_album_name": None,
                "lastfm_album_mbid": None,
                "lastfm_album_url": None,
                "lastfm_album_listeners": None,
                "lastfm_album_playcount": None,
                "lastfm_album_match_status": "error_or_not_found",
            }
            try:
                data = call_lastfm(
                    session, api_key, "album.getInfo", artist="The Weeknd", album=album_name, autocorrect=1
                )
                a = data.get("album", {})
                row.update({
                    "lastfm_album_name": a.get("name"),
                    "lastfm_album_mbid": a.get("mbid"),
                    "lastfm_album_url": a.get("url"),
                    "lastfm_album_listeners": a.get("listeners"),
                    "lastfm_album_playcount": a.get("playcount"),
                    "lastfm_album_match_status": "matched" if a else "empty_response",
                })
            except Exception as exc:
                log_rows.append({"kind": "album", "query": album_name, "error": str(exc)})
            album_rows.append(row)
            if i % 15 == 0 or i == len(album_names):
                print(f"Album lookups: {i}/{len(album_names)}")
            time.sleep(PAUSE_SECONDS)

    track_stats = pd.DataFrame.from_records(
        [{"track": title, **values} for title, values in track_cache.items()]
    )
    # Preserve every release appearance and all original catalogue/audit columns.
    output = df.merge(track_stats, on="track", how="left", validate="many_to_one")
    output.to_csv(TRACK_OUT, index=False)
    pd.DataFrame(album_rows).to_csv(ALBUM_OUT, index=False)
    pd.DataFrame(log_rows, columns=["kind", "query", "error"]).to_csv(LOG_OUT, index=False)

    matched = int((output["lastfm_track_match_status"] == "matched").sum())
    print("\nCollection complete.")
    print(f"Track appearances in output: {len(output)}")
    print(f"Track appearances with a Last.fm match: {matched}/{len(output)}")
    print(f"Unique track titles queried: {len(titles)}")
    print(f"Release titles queried: {len(album_names)}")
    print(f"API errors / misses logged: {len(log_rows)}")
    print(f"Saved: {TRACK_OUT}, {ALBUM_OUT}, {LOG_OUT}")
    print("Review the collection log and verify uncertain title matches before analysis.")


if __name__ == "__main__":
    main()
