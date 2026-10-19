"""Rebuild track stats by deduplicating on the RESOLVED lastfm_url.

Last.fm redirects multiple search hits to the same canonical URL. Two entries
with the same resolved URL are the same recording, even if their MBIDs were
empty or their names/artists differ. This script deduplicates by URL, falling
back to (name, artist) only when URL is empty.

Outputs:
  - weeknd_lastfm_track_stats_v5.csv
  - weeknd_lastfm_track_matches_v5.csv
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

MATCHES = Path("weeknd_lastfm_track_matches_v4.csv")
STATS_V4 = Path("weeknd_lastfm_track_stats_v4.csv")
STATS_OUT = Path("weeknd_lastfm_track_stats_v5.csv")
MATCH_OUT = Path("weeknd_lastfm_track_matches_v5.csv")

# Manual overrides for entries that search finds but getInfo refuses to resolve.
TRACK_OVERRIDES: dict[tuple[str, str], dict[str, Any]] = {
    ("I Was Never There", "The Weeknd"): {
        "lastfm_listeners": 970785,
        "note": "Manual override: search finds 970,785 listeners; getInfo rejects.",
    },
}


def clean(v: Any) -> str:
    if pd.isna(v): return ""
    return re.sub(r"\s+", " ", str(v)).strip()


def main():
    matches = pd.read_csv(MATCHES)
    stats = pd.read_csv(STATS_V4)

    resolved = matches[matches["decision"] == "kept"].copy()
    resolved["lastfm_mbid"] = resolved["lastfm_mbid"].fillna("").astype(str).str.strip()
    resolved["lastfm_url"] = resolved["lastfm_url"].fillna("").astype(str).str.strip()
    resolved["lastfm_playcount"] = pd.to_numeric(
        resolved["lastfm_playcount"], errors="coerce")

    resolved = resolved.sort_values(
        ["spotify_title", "spotify_first_artist", "rank"]).reset_index(drop=True)

    # Dedup: URL first (most reliable), then (name, artist) as fallback.
    keep_mask = []
    seen_url: dict[tuple[str, str], set[str]] = {}
    seen_name_artist: dict[tuple[str, str], set[tuple[str, str]]] = {}

    for _, r in resolved.iterrows():
        key = (r["spotify_title"], r["spotify_first_artist"])
        url = r["lastfm_url"]
        name_artist = (clean(r["lastfm_name"]), clean(r["lastfm_artist"]))

        if url:
            seen = seen_url.setdefault(key, set())
            if url in seen:
                keep_mask.append(False)
                continue
            seen.add(url)
            keep_mask.append(True)
        else:
            seen = seen_name_artist.setdefault(key, set())
            if name_artist in seen:
                keep_mask.append(False)
                continue
            seen.add(name_artist)
            keep_mask.append(True)

    resolved["kept_in_v5"] = keep_mask

    deduped = resolved[resolved["kept_in_v5"]].copy()

    # Aggregate per track title.
    grouped = deduped.groupby("spotify_title").agg({
        "lastfm_listeners_detail": lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum(),
        "lastfm_playcount": lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum(),
    }).rename(columns={
        "lastfm_listeners_detail": "lastfm_track_listeners",
        "lastfm_playcount": "lastfm_track_playcount",
    })
    grouped["lastfm_match_count"] = deduped.groupby("spotify_title").size()

    # Apply manual overrides.
    for (title, _artist), ov in TRACK_OVERRIDES.items():
        if title not in grouped.index:
            continue
        if ov.get("lastfm_listeners"):
            grouped.at[title, "lastfm_track_listeners"] = (
                pd.to_numeric(grouped.at[title, "lastfm_track_listeners"], errors="coerce") or 0
            ) + ov["lastfm_listeners"]
            grouped.at[title, "lastfm_match_count"] = (
                pd.to_numeric(grouped.at[title, "lastfm_match_count"], errors="coerce") or 0
            ) + 1

    grouped = grouped.reset_index().rename(columns={"spotify_title": "track"})

    # Merge onto v4 stats, replacing only the Last.fm columns.
    v5 = stats.drop(columns=[
        "lastfm_match_count", "lastfm_track_listeners",
        "lastfm_track_playcount", "lastfm_match_status",
        "lastfm_top_match_name", "lastfm_top_match_artist",
    ], errors="ignore").merge(grouped, on="track", how="left")

    v5["lastfm_match_status"] = v5["lastfm_track_listeners"] \
        .apply(lambda v: "matched" if pd.notna(v) and v > 0 else "no_valid_match")
    v5["lastfm_top_match_name"] = v5["track"]
    v5["lastfm_top_match_artist"] = v5["track"].map(
        stats.groupby("track")["lastfm_top_match_artist"].first())

    v5.to_csv(STATS_OUT, index=False)

    resolved["decision_v5"] = resolved["kept_in_v5"].map(
        {True: "kept", False: "rejected_duplicate"})
    resolved.to_csv(MATCH_OUT, index=False)

    print(f"Wrote {STATS_OUT.name}")
    print(f"Wrote {MATCH_OUT.name}")

    check = v5[v5["track"].isin([
        "House Of Balloons / Glass Table Girls",
        "The Party & The After Party",
        "The Birds Pt. 1", "The Birds Pt. 2",
        "XO / The Host", "Live For", "Love Me Harder",
        "I Was Never There", "Next",
        "Reflections Laughing (feat. Travis Scott, Florence + The Machine)",
    ])][["track", "lastfm_match_count",
         "lastfm_track_listeners", "lastfm_track_playcount",
         "lastfm_match_status"]]
    print("\n--- Sanity check ---")
    print(check.to_string(index=False))


if __name__ == "__main__":
    main()