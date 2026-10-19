"""Collect Last.fm statistics using each track's first credited artist.

Inputs (same folder):
  - weeknd_tracks_audited_final.csv
  - .env containing LASTFM_API_KEY=your_key

Outputs (corrected versions, preserving the original collection):
  - weeknd_lastfm_track_stats_corrected.csv
  - weeknd_lastfm_album_stats_corrected.csv
  - weeknd_lastfm_collection_log_corrected.csv

Run: python collect_weeknd_lastfm_corrected.py
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
TRACK_OUT = Path("weeknd_lastfm_track_stats_corrected.csv")
ALBUM_OUT = Path("weeknd_lastfm_album_stats_corrected.csv")
LOG_OUT = Path("weeknd_lastfm_collection_log_corrected.csv")
PAUSE_SECONDS = 0.25


def clean_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def first_credited_artist(value: Any) -> str:
    """Spotify's artists field is stored as comma-separated credited names."""
    artists = clean_text(value)
    if not artists:
        return "The Weeknd"
    # In this catalogue, the first listed artist is the lead/primary credit.
    # Keep the remaining artist credits in the original CSV for collaboration analysis.
    return artists.split(",", 1)[0].strip() or "The Weeknd"


def safe_error(exc: Exception) -> str:
    """Avoid logging request URLs, which can contain the Last.fm API key."""
    message = str(exc)
    message = re.sub(r"https?://\S+", "[URL omitted]", message)
    message = re.sub(r"(?i)(api_key=)[^&\s]+", r"\1[REDACTED]", message)
    return message[:500]


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

    # Use (track title, first credited artist) as the lookup/cache key. This prevents
    # same-titled tracks by different lead artists from sharing a Last.fm result.
    df["lastfm_query_artist"] = df["artists"].apply(first_credited_artist)
    df["_track_key"] = list(zip(df["track"].map(clean_text), df["lastfm_query_artist"]))
    track_keys = sorted({key for key in df["_track_key"] if key[0]})
    track_cache: dict[tuple[str, str], dict[str, Any]] = {}
    log_rows: list[dict[str, Any]] = []

    with requests.Session() as session:
        for i, (title, artist) in enumerate(track_keys, start=1):
            try:
                data = call_lastfm(
                    session, api_key, "track.getInfo",
                    artist=artist, track=title, autocorrect=1
                )
                t = data.get("track", {})
                track_cache[(title, artist)] = {
                    "lastfm_query_artist": artist,
                    "lastfm_track_name": t.get("name"),
                    "lastfm_track_artist": (
                        t.get("artist", {}).get("name")
                        if isinstance(t.get("artist"), dict)
                        else t.get("artist")
                    ),
                    "lastfm_track_mbid": t.get("mbid"),
                    "lastfm_track_url": t.get("url"),
                    "lastfm_track_listeners": t.get("listeners"),
                    "lastfm_track_playcount": t.get("playcount"),
                    "lastfm_track_match_status": "matched" if t else "empty_response",
                }
                if not t:
                    log_rows.append({
                        "kind": "track", "query_artist": artist, "query_title": title,
                        "error": "Empty response; verify this artist/title manually."
                    })
            except Exception as exc:
                track_cache[(title, artist)] = {
                    "lastfm_query_artist": artist,
                    "lastfm_track_name": None,
                    "lastfm_track_artist": None,
                    "lastfm_track_mbid": None,
                    "lastfm_track_url": None,
                    "lastfm_track_listeners": None,
                    "lastfm_track_playcount": None,
                    "lastfm_track_match_status": "error_or_not_found",
                }
                log_rows.append({
                    "kind": "track", "query_artist": artist, "query_title": title,
                    "error": safe_error(exc)
                })
            if i % 25 == 0 or i == len(track_keys):
                print(f"Track lookups: {i}/{len(track_keys)}")
            time.sleep(PAUSE_SECONDS)

        # Album-level stats are queried separately. "Trilogy (bonus)" is an internal
        # catalogue label rather than a real release title, so skip that synthetic label.
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
                "lastfm_album_match_status": "skipped_synthetic_label" if album_name == "Trilogy (bonus)" else "error_or_not_found",
            }
            if album_name == "Trilogy (bonus)":
                log_rows.append({
                    "kind": "album", "query_artist": "The Weeknd", "query_title": album_name,
                    "error": "Skipped: internal bonus-track label, not a Last.fm release title."
                })
                album_rows.append(row)
                continue
            try:
                data = call_lastfm(
                    session, api_key, "album.getInfo",
                    artist="The Weeknd", album=album_name, autocorrect=1
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
                if not a:
                    log_rows.append({
                        "kind": "album", "query_artist": "The Weeknd", "query_title": album_name,
                        "error": "Empty response; verify this release title manually."
                    })
            except Exception as exc:
                log_rows.append({
                    "kind": "album", "query_artist": "The Weeknd", "query_title": album_name,
                    "error": safe_error(exc)
                })
            album_rows.append(row)
            if i % 15 == 0 or i == len(album_names):
                print(f"Album lookups: {i}/{len(album_names)}")
            time.sleep(PAUSE_SECONDS)

    track_stats = pd.DataFrame.from_records([
        {"track": title, "lastfm_query_artist": artist, **values}
        for (title, artist), values in track_cache.items()
    ])
    # Remove temporary key before merging, then preserve all catalogue/audit columns.
    df = df.drop(columns=["lastfm_query_artist", "_track_key"])
    df["_track_key"] = list(zip(df["track"].map(clean_text), df["artists"].apply(first_credited_artist)))
    track_stats["_track_key"] = list(zip(track_stats["track"].map(clean_text), track_stats["lastfm_query_artist"]))
    output = df.merge(track_stats.drop(columns=["track"]), on="_track_key", how="left", validate="many_to_one")
    output = output.drop(columns=["_track_key"])
    output.to_csv(TRACK_OUT, index=False)
    pd.DataFrame(album_rows).to_csv(ALBUM_OUT, index=False)
    pd.DataFrame(log_rows, columns=["kind", "query_artist", "query_title", "error"]).to_csv(LOG_OUT, index=False)

    matched = int((output["lastfm_track_match_status"] == "matched").sum())
    unique_matched = int((track_stats["lastfm_track_match_status"] == "matched").sum())
    print("\nCorrected collection complete.")
    print(f"Track appearances in output: {len(output)}")
    print(f"Track appearances with a Last.fm match: {matched}/{len(output)}")
    print(f"Unique (title, lead artist) pairs queried: {len(track_keys)}")
    print(f"Unique pairs matched: {unique_matched}/{len(track_keys)}")
    print(f"Release titles processed: {len(album_names)}")
    print(f"API misses / errors logged: {len(log_rows)}")
    print(f"Saved: {TRACK_OUT}, {ALBUM_OUT}, {LOG_OUT}")
    print("The log omits request URLs and API keys. Manually verify unusual matches before analysis.")


if __name__ == "__main__":
    main()


TRACK_ALIASES = {
    "I Was Never There": "I Was Never There",
    "Reflections Laughing (feat. Travis Scott, Florence + The Machine)": "Reflections Laughing",
}