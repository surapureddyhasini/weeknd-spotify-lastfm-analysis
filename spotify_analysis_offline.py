"""Collect and prepare The Weeknd's Spotify release/track catalogue.

Outputs
-------
weeknd_tracks_raw.csv
    One row per track appearance on a Spotify release. Duplicates are preserved.
weeknd_tracks_clean.csv
    Enriched release-track table with release type, era, ISRC, and inclusion flags.

Important metric rules
----------------------
- `in_default_view` excludes duplicate tracks on the Trilogy compilation, but retains
  unique Trilogy bonus tracks as `Trilogy (bonus)` in the Mixtape era.
- `is_primary_track` selects one row per recording (ISRC where available, otherwise
  Spotify track ID) for catalogue-wide counts. Do not use it for album-by-album charts,
  because a track can legitimately appear on multiple releases.
- For cross-release matching of Trilogy tracks where ISRC is unavailable, a normalized
  title + credited-artist fallback is used only against the three original mixtapes.

Run: python spotify_analysis.py
Dependencies: pip install spotipy pandas python-dotenv
.env: SPOTIFY_CLIENT_ID=... and SPOTIFY_CLIENT_SECRET=...
"""

import json
import os
import re
import time
import unicodedata
from typing import Any

import pandas as pd

WEEKND_ID = "1Xyo4u8uXC1ZmMpatF05PJ"
WEEKND_NAME = "The Weeknd"
PAGE = 10  # Keep at 10 to work with Spotify Development Mode limits.

RELEASE_TYPES = {
    "house of balloons": "Mixtape",
    "thursday": "Mixtape",
    "echoes of silence": "Mixtape",
    "trilogy": "Compilation",
    "kiss land": "Studio album",
    "beauty behind the madness": "Studio album",
    "starboy": "Studio album",
    "after hours": "Studio album",
    "dawn fm": "Studio album",
    "dawn fm (alternate world)": "Studio album",
    "live at sofi stadium": "Live album",
    "hurry up tomorrow": "Studio album",
    "my dear melancholy,": "EP",
    "my dear melancholy": "EP",
}

MIXTAPE_NAMES = {"house of balloons", "thursday", "echoes of silence"}

ERAS = [
    ("2011-01-01", "Mixtape era"),
    ("2013-09-01", "Kiss Land"),
    ("2015-01-01", "Beauty Behind the Madness"),
    ("2016-11-01", "Starboy"),
    ("2020-01-01", "After Hours"),
    ("2021-12-01", "Dawn FM"),
    ("2025-01-01", "Hurry Up Tomorrow"),
]

EDITION_PATTERN = re.compile(
    r"\s*[\(\[][^)\]]*(deluxe|expanded|remaster|edition|version|bonus|"
    r"explicit|clean|anniversary|original)[^)\]]*[\)\]]",
    flags=re.IGNORECASE,
)


def normalize_text(value: Any) -> str:
    """Normalize text for cautious matching; this is not a universal song identity."""
    if value is None or pd.isna(value):
        return ""
    value = unicodedata.normalize("NFKD", str(value))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = EDITION_PATTERN.sub("", value)
    value = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return re.sub(r"\s+", " ", value).strip()


def clean_name(name: str) -> str:
    return EDITION_PATTERN.sub("", str(name or "")).strip().lower()


def connect():
    # Keep data-cleaning functions importable for offline tests without API packages.
    try:
        import spotipy
        from dotenv import load_dotenv
        from spotipy.oauth2 import SpotifyClientCredentials
    except ImportError as exc:
        raise SystemExit(
            "Missing API dependencies. Install them with: pip install spotipy python-dotenv"
        ) from exc
    load_dotenv()
    cid = os.getenv("SPOTIFY_CLIENT_ID")
    secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not cid or not secret:
        raise SystemExit("Missing SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET in .env")
    sp = spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(client_id=cid, client_secret=secret),
        retries=5,
        requests_timeout=20,
    )
    sp.artist(WEEKND_ID)
    print("Spotify API connection successful!")
    return sp


def fetch_albums(sp):
    """Fetch album, single, and compilation releases, paging until exhausted."""
    albums, offset = [], 0
    while True:
        page = sp.artist_albums(
            WEEKND_ID,
            album_type="album,single,compilation",
            limit=PAGE,
            offset=offset,
        )
        albums.extend(page.get("items", []))
        if not page.get("next"):
            break
        offset += PAGE
    # Spotify can return the same release more than once across pagination/markets.
    unique = {}
    for album in albums:
        unique.setdefault(album.get("id"), album)
    result = [a for a in unique.values() if a.get("id")]
    print(f"Found {len(result)} unique releases")
    return result


def fetch_tracks(sp, albums):
    """Return one row per track appearance, retaining release membership."""
    rows = []
    for i, album in enumerate(albums, 1):
        offset = 0
        while True:
            page = sp.album_tracks(album["id"], limit=PAGE, offset=offset)
            for t in page.get("items", []):
                artists = [a.get("name", "") for a in t.get("artists", [])]
                rows.append({
                    "album_id": album.get("id"),
                    "album": album.get("name", "Unknown release"),
                    "api_album_type": album.get("album_type", "unknown"),
                    "release_date": album.get("release_date"),
                    "track_id": t.get("id"),
                    "track": t.get("name", "Unknown track"),
                    "track_number": t.get("track_number"),
                    "disc_number": t.get("disc_number", 1),
                    "duration_ms": t.get("duration_ms"),
                    "duration_min": (t.get("duration_ms") or 0) / 60000,
                    "explicit": t.get("explicit"),
                    "artists": ", ".join(artists),
                    "n_artists": len(artists),
                })
            if not page.get("next"):
                break
            offset += PAGE
        if i % 10 == 0:
            print(f"  ...{i}/{len(albums)} releases done")
        time.sleep(0.1)
    return pd.DataFrame(rows)


def fetch_isrcs(sp, track_ids, cache_path="weeknd_isrc_cache.json", delay=0.1):
    """Fetch ISRCs with individual track requests and a persistent local cache.

    Spotify removed the batch GET /tracks endpoint for affected Development Mode
    apps. This function uses GET /tracks/{id} via ``sp.track`` instead. If Spotify
    returns 403, it stops further enrichment requests and continues with the
    available cache; the rest of the catalogue pipeline does not depend on ISRCs.
    """
    ids = list(dict.fromkeys(
        str(x) for x in track_ids if pd.notna(x) and str(x).strip()
    ))

    cache = {}
    try:
        with open(cache_path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            cache = {str(k): (v or "") for k, v in loaded.items()}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    # Cached empty strings represent successful lookups where Spotify returned no ISRC.
    isrc_by_id = {track_id: cache[track_id] for track_id in ids if track_id in cache}
    fetched = 0
    blocked = False

    for track_id in ids:
        if track_id in cache:
            continue
        try:
            track = sp.track(track_id)
            isrc = (track.get("external_ids") or {}).get("isrc", "")
            cache[track_id] = isrc or ""
            isrc_by_id[track_id] = isrc or ""
            fetched += 1
        except Exception as exc:
            status = getattr(exc, "http_status", None)
            response = getattr(exc, "response", None)
            if status is None and response is not None:
                status = getattr(response, "status_code", None)
            print(f"Warning: could not fetch ISRC for track {track_id}: {exc}")
            if status == 403 or "403" in str(exc):
                print(
                    "Spotify returned 403 for individual track lookup; stopping ISRC "
                    "enrichment. The script will continue using cached ISRCs and "
                    "Spotify track IDs/title-artist matching."
                )
                blocked = True
                break
        if delay:
            time.sleep(delay)

    # Persist successful lookups, including successful lookups with no ISRC.
    try:
        with open(cache_path, "w", encoding="utf-8") as handle:
            json.dump(cache, handle, indent=2, sort_keys=True)
    except OSError as exc:
        print(f"Warning: could not save ISRC cache to {cache_path}: {exc}")

    if fetched:
        print(f"Fetched ISRC metadata for {fetched} tracks; cache: {cache_path}")
    if blocked:
        print("ISRC enrichment was partial; catalogue CSVs can still be generated.")
    return isrc_by_id


def label_release(row):
    key = clean_name(row.get("album", ""))
    if key in RELEASE_TYPES:
        return RELEASE_TYPES[key]
    if row.get("api_album_type") == "single":
        return "Single"
    if row.get("api_album_type") == "compilation":
        return "Compilation"
    return "Unclassified"


def assign_era(date):
    if pd.isna(date):
        return None
    era = "Pre-2011"
    for start, name in ERAS:
        if date >= pd.Timestamp(start):
            era = name
    return era


def build_clean(raw, isrc_by_id=None):
    """Enrich raw rows and create explicit, auditable inclusion flags."""
    if raw.empty:
        return raw.copy()

    df = raw.copy()
    isrc_by_id = isrc_by_id or {}
    df["release_date"] = pd.to_datetime(df["release_date"], errors="coerce")
    df["year"] = df["release_date"].dt.year.astype("Int64")
    df["release_type"] = df.apply(label_release, axis=1)
    df["track_clean"] = df["track"].map(normalize_text)
    df["artists_clean"] = df["artists"].map(normalize_text)
    df["isrc"] = df["track_id"].map(isrc_by_id).fillna("")

    df["collaborators"] = df["artists"].map(
        lambda s: ", ".join(
            a.strip() for a in str(s).split(",")
            if a.strip() and normalize_text(a) != normalize_text(WEEKND_NAME)
        )
    )
    df["n_collaborators"] = df["collaborators"].map(
        lambda s: len([x for x in s.split(",") if x.strip()]) if s else 0
    )
    df["is_collab"] = df["n_collaborators"] > 0
    df["era"] = df["release_date"].map(assign_era)
    df = df.sort_values(["release_date", "album", "disc_number", "track_number"], na_position="last").reset_index(drop=True)

    # Strong identity: ISRC; fallback: Spotify track ID. Never dedupe globally by title alone.
    df["recording_key"] = df.apply(
        lambda r: f"isrc:{r['isrc']}" if r["isrc"] else f"spotify:{r['track_id']}", axis=1
    )
    df["is_primary_track"] = ~df.duplicated(subset="recording_key", keep="first")

    # Identify Trilogy duplicates against the three original mixtapes. Prefer ISRC;
    # use normalized title + credited artists only when ISRC is missing on either side.
    df["is_duplicate_of_other_release"] = False
    trilogy_mask = df["release_type"].eq("Compilation") & df["album"].map(clean_name).eq("trilogy")
    mixtape_mask = df["album"].map(clean_name).isin(MIXTAPE_NAMES)
    mixtapes = df.loc[mixtape_mask]
    mixtape_isrcs = set(mixtapes.loc[mixtapes["isrc"].ne(""), "isrc"])
    mixtape_title_artist = set(zip(mixtapes["track_clean"], mixtapes["artists_clean"]))
    mixtape_title_artist_without_isrc = set(
        zip(
            mixtapes.loc[mixtapes["isrc"].eq(""), "track_clean"],
            mixtapes.loc[mixtapes["isrc"].eq(""), "artists_clean"],
        )
    )

    for idx in df.index[trilogy_mask]:
        isrc = df.at[idx, "isrc"]
        title_artist = (df.at[idx, "track_clean"], df.at[idx, "artists_clean"])
        if isrc:
            # Trust a known ISRC. Use title/artist fallback only if the matching
            # mixtape appearance has no ISRC available for comparison.
            duplicate = (isrc in mixtape_isrcs) or (
                title_artist in mixtape_title_artist_without_isrc
            )
        else:
            duplicate = title_artist in mixtape_title_artist
        if duplicate:
            df.at[idx, "is_duplicate_of_other_release"] = True

    # Unique Trilogy tracks are retained, visibly labelled as bonus tracks in Mixtape era.
    bonus_mask = trilogy_mask & ~df["is_duplicate_of_other_release"]
    df.loc[bonus_mask, "album"] = "Trilogy (bonus)"
    df.loc[bonus_mask, "release_type"] = "Mixtape"
    df.loc[bonus_mask, "era"] = "Mixtape era"

    # Keep all release appearances in the file; use flags to choose the correct rows per chart.
    df["in_default_view"] = ~(
        df["is_duplicate_of_other_release"] & df["api_album_type"].notna()
    )
    # Only duplicate appearances on Trilogy are switched off by default. Other duplicate
    # appearances remain available for release-specific charts but are not primary catalogue rows.
    df["in_default_view"] = df["in_default_view"] & ~(
        df["is_duplicate_of_other_release"] & df["album"].map(clean_name).eq("trilogy")
    )
    df["count_in_catalogue"] = df["in_default_view"] & df["is_primary_track"]

    # Remove helper fields that are not needed in the dashboard CSV.
    return df.drop(columns=["track_clean", "artists_clean"]).reset_index(drop=True)


def main():
    """Process the saved raw CSV locally; this default workflow makes no Spotify API calls."""
    from pathlib import Path
    import json

    project_dir = Path(__file__).resolve().parent
    raw_path = project_dir / "weeknd_tracks_raw.csv"
    clean_path = project_dir / "weeknd_tracks_clean.csv"
    cache_path = project_dir / "weeknd_isrc_cache.json"

    if not raw_path.exists():
        raise SystemExit(
            "Could not find weeknd_tracks_raw.csv beside this script. "
            "Place the script and CSV in the same project folder."
        )

    raw = pd.read_csv(raw_path)
    print(f"Loaded existing raw catalogue: {len(raw)} rows")
    print("Offline mode: no Spotify API requests will be made.")

    isrc_by_id = {}
    try:
        with cache_path.open("r", encoding="utf-8") as handle:
            cache = json.load(handle)
        if isinstance(cache, dict):
            isrc_by_id = {str(k): (v or "") for k, v in cache.items()}
            print(f"Loaded cached ISRC entries: {len(isrc_by_id)}")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        print("No readable ISRC cache found; continuing without ISRC enrichment.")

    clean = build_clean(raw, isrc_by_id)
    clean.to_csv(clean_path, index=False)
    print(f"Clean release-track rows saved: {len(clean)} -> {clean_path.name}")
    print(f"Unique catalogue recordings (default): {int(clean['count_in_catalogue'].sum())}")
    print("\nRows per release type:")
    print(clean["release_type"].value_counts(dropna=False).to_string())
    print("\nDefault-view rows per era:")
    print(clean.loc[clean["in_default_view"], "era"].value_counts(dropna=False).to_string())
    print("\nTrilogy duplicate rows excluded by default:",
          int(clean["is_duplicate_of_other_release"].sum()))
    print("Trilogy bonus rows retained:",
          int(clean["album"].eq("Trilogy (bonus)").sum()))

    unclassified = clean.loc[clean["release_type"].eq("Unclassified"), "album"].dropna().unique()
    if len(unclassified):
        print("\nUnclassified releases - review RELEASE_TYPES:")
        for album in unclassified:
            print("  -", album)


if __name__ == "__main__":
    main()

