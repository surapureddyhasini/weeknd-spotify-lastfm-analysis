"""Collect Last.fm stats with fragmentation-aware aggregation (Option B v4).

Fixes vs v3:
  - Deduplicate matches by MBID (Last.fm returns multiple search hits pointing
    at the same recording; counting them separately inflates totals).
  - Fetch track stats by MBID when available (bypasses title-matching quirks).
  - Fall back to (name, artist) dedup only when MBID is empty.

Outputs:
  - weeknd_lastfm_track_stats_v4.csv
  - weeknd_lastfm_track_matches_v4.csv
  - weeknd_lastfm_album_stats_v4.csv
  - weeknd_lastfm_collection_log_v4.csv
"""
from __future__ import annotations

import os, re, time, unicodedata
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

BASE = "https://ws.audioscrobbler.com/2.0/"
INPUT = Path("weeknd_tracks_audited_final.csv")
TRACK_OUT = Path("weeknd_lastfm_track_stats_v4.csv")
MATCH_OUT = Path("weeknd_lastfm_track_matches_v4.csv")
ALBUM_OUT = Path("weeknd_lastfm_album_stats_v4.csv")
LOG_OUT = Path("weeknd_lastfm_collection_log_v4.csv")
PAUSE = 0.20
TOP_N = 10
RETRIES = 3


# ---------- text helpers ----------

def clean_text(v: Any) -> str:
    if pd.isna(v): return ""
    return re.sub(r"\s+", " ", str(v)).strip()


def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


_TITLE_SUFFIX_PATTERNS = [
    r"\s*[\(\[]\s*(?:feat\.?|ft\.?|with|from)[^\)\]]*[\)\]]\s*$",
    r"\s*-\s*(?:feat\.?|ft\.?)\s+.*$",
    r"\s*[\(\[]\s*(?:bonus\s+track|explicit|clean|audio|official\s+audio|"
    r"official\s+video|lyric\s+video|visualizer|animated|instrumental|"
    r"a\s*cappella|acapella|sped\s+up|slowed|extended|single\s+version|"
    r"radio\s+edit|album\s+version|original)\s*[\)\]]\s*$",
    r"\s*-\s*(?:bonus\s+track|explicit|clean|audio|official\s+audio|"
    r"official\s+video|lyric\s+video|visualizer|animated|instrumental|"
    r"a\s*cappella|acapella|sped\s+up|slowed|extended|single\s+version|"
    r"radio\s+edit|album\s+version|original)\s*$",
    r"\s*\[\s*(?:bonus\s+track|explicit|clean)\s*\]\s*$",
    r"\s*-\s*original\s*$",
]
_TITLE_SUFFIX_COMPILED = [re.compile(p, re.IGNORECASE) for p in _TITLE_SUFFIX_PATTERNS]


def normalize_title(s: str) -> str:
    s = clean_text(s)
    s = strip_accents(s)
    changed = True
    while changed and s:
        changed = False
        for pat in _TITLE_SUFFIX_COMPILED:
            new = pat.sub("", s)
            if new != s:
                s = new
                changed = True
    s = re.sub(r"^\d+[\.\s]+", "", s)
    s = s.replace("’", "'").replace("‘", "'")
    s = re.sub(r"[^a-z0-9']+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def titles_match(spotify_title: str, lastfm_name: str) -> bool:
    a = normalize_title(spotify_title)
    b = normalize_title(lastfm_name)
    if not a or not b:
        return False
    return a == b


# ---------- artist helpers ----------

_ARTIST_SPLIT = re.compile(
    r"\s*(?:,|&|;|/|\be\b|\by\b|\band\b|\bfeat\.?\b|\bft\.?\b|\bwith\b)\s*",
    flags=re.IGNORECASE,
)


def artist_set(s: str) -> frozenset[str]:
    s = clean_text(s)
    if not s: return frozenset()
    return frozenset(
        strip_accents(p).lower().strip(" .")
        for p in _ARTIST_SPLIT.split(s)
        if p.strip()
    )


def spotify_artist_set(artists_field: str) -> frozenset[str]:
    parts = [clean_text(a) for a in str(artists_field).split(",")]
    return frozenset(strip_accents(p).lower() for p in parts if p)


def artists_match(lastfm_artist: str, spotify_artists: frozenset[str]) -> bool:
    lf = artist_set(lastfm_artist)
    return bool(lf) and lf.issubset(spotify_artists)


# ---------- Last.fm calls ----------

def _raw_get(session, params, timeout=25):
    r = session.get(BASE, params=params, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"Last.fm error {data.get('error')}: {data.get('message','')}")
    return data


def call(session, api_key, method, **params):
    payload = {"method": method, "api_key": api_key, "format": "json", **params}
    last_exc = None
    for attempt in range(1, RETRIES + 1):
        try:
            return _raw_get(session, payload)
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            if attempt < RETRIES:
                time.sleep(2.0 * attempt)
        except RuntimeError:
            raise
    raise last_exc if last_exc else RuntimeError("call failed")


def safe_err(e: Exception) -> str:
    m = str(e)
    m = re.sub(r"https?://\S+", "[URL omitted]", m)
    m = re.sub(r"(?i)(api_key=)[^&\s]+", r"\1[REDACTED]", m)
    return m[:400]


def get_info_by_mbid(session, api_key, mbid):
    if not mbid:
        return None, "no_mbid"
    try:
        data = call(session, api_key, "track.getInfo", mbid=mbid, autocorrect=1)
        t = data.get("track", {})
        if t:
            return t, "mbid"
    except Exception as exc:
        return None, f"mbid_failed: {safe_err(exc)}"
    return None, "mbid_empty_response"


def get_info_by_title(session, api_key, name, artist):
    last = "failed"
    for ac in (1, 0):
        try:
            data = call(session, api_key, "track.getInfo",
                        artist=artist, track=name, autocorrect=ac)
            t = data.get("track", {})
            if t:
                return t, f"title_autocorrect={ac}"
        except Exception as exc:
            last = safe_err(exc)
            continue
    return None, f"title_failed: {last}"


# ---------- main ----------

def main():
    load_dotenv()
    api_key = os.getenv("LASTFM_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("LASTFM_API_KEY missing.")
    if not INPUT.exists():
        raise SystemExit(f"Cannot find {INPUT.resolve()}.")

    df = pd.read_csv(INPUT)
    df["_title"] = df["track"].map(clean_text)
    df["_spotify_artists"] = df["artists"].map(spotify_artist_set)
    df["_first_artist"] = df["artists"].map(lambda s: clean_text(str(s).split(",")[0]))

    keys = {}
    for _, row in df.iterrows():
        k = (row["_title"], row["_spotify_artists"])
        if k[0]:
            keys.setdefault(k, row["_first_artist"])
    key_list = sorted(keys.items(), key=lambda x: x[0][0])
    print(f"Looking up {len(key_list)} unique (title, artist-set) pairs")

    match_rows: list[dict] = []
    agg: dict[tuple[str, frozenset[str]], dict[str, Any]] = {}
    log_rows: list[dict] = []

    with requests.Session() as session:
        for i, ((title, spotify_artists), first_artist) in enumerate(key_list, 1):
            # --- 1. search ---
            try:
                data = call(session, api_key, "track.search", track=title, limit=TOP_N)
                hits = data.get("results", {}).get("trackmatches", {}).get("track", [])
            except Exception as exc:
                hits = []
                log_rows.append({"kind": "track_search", "title": title,
                                 "artist": first_artist, "error": safe_err(exc)})

            # --- 2. filter by artist + title ---
            kept: list[dict] = []
            for rank, h in enumerate(hits, 1):
                lf_name = h.get("name", "")
                lf_artist = h.get("artist", "")
                mbid = h.get("mbid") or ""
                rec = {
                    "spotify_title": title,
                    "spotify_first_artist": first_artist,
                    "rank": rank,
                    "lastfm_name": lf_name,
                    "lastfm_artist": lf_artist,
                    "lastfm_mbid": mbid,
                    "lastfm_listeners": h.get("listeners"),
                }
                if not artists_match(lf_artist, spotify_artists):
                    rec["decision"] = "rejected_artist"
                    match_rows.append(rec); continue
                if not titles_match(title, lf_name):
                    rec["decision"] = "rejected_title"
                    match_rows.append(rec); continue
                rec["decision"] = "kept"
                kept.append(rec)

            # --- 3. dedup by MBID first, then (name, artist) for MBID-less entries ---
            seen_mbid: set[str] = set()
            seen_name_artist: set[tuple[str, str]] = set()
            deduped: list[dict] = []
            for r in kept:
                if r["lastfm_mbid"]:
                    if r["lastfm_mbid"] in seen_mbid:
                        r["decision"] = "rejected_duplicate_mbid"
                        match_rows.append(r); continue
                    seen_mbid.add(r["lastfm_mbid"])
                else:
                    k = (r["lastfm_name"], r["lastfm_artist"])
                    if k in seen_name_artist:
                        r["decision"] = "rejected_duplicate_name"
                        match_rows.append(r); continue
                    seen_name_artist.add(k)
                deduped.append(r)

            # --- 4. fetch stats per kept unique entry ---
            listeners_total = 0
            playcount_total = 0
            for r in deduped:
                t, how = (None, "")
                if r["lastfm_mbid"]:
                    t, how = get_info_by_mbid(session, api_key, r["lastfm_mbid"])
                if t is None:
                    t, how = get_info_by_title(
                        session, api_key, r["lastfm_name"], r["lastfm_artist"])
                if t is None:
                    r["decision"] = "getinfo_failed"
                    r["error"] = how
                    log_rows.append({
                        "kind": "track_getInfo",
                        "title": r["lastfm_name"],
                        "artist": r["lastfm_artist"],
                        "error": how,
                    })
                else:
                    r["lastfm_playcount"] = t.get("playcount")
                    r["lastfm_listeners_detail"] = t.get("listeners")
                    r["lastfm_url"] = t.get("url")
                    r["getinfo_variant"] = how
                    listeners_total += int(t.get("listeners") or 0)
                    playcount_total += int(t.get("playcount") or 0)
                match_rows.append(r)
                time.sleep(PAUSE)

            resolved = [r for r in deduped if r.get("lastfm_playcount") is not None]
            agg[(title, spotify_artists)] = {
                "lastfm_match_count": len(resolved),
                "lastfm_track_listeners": listeners_total or None,
                "lastfm_track_playcount": playcount_total or None,
                "lastfm_match_status": "matched" if resolved else "no_valid_match",
                "lastfm_top_match_name": resolved[0]["lastfm_name"] if resolved else None,
                "lastfm_top_match_artist": resolved[0]["lastfm_artist"] if resolved else None,
            }

            if i % 25 == 0 or i == len(key_list):
                print(f"  {i}/{len(key_list)}")
            time.sleep(PAUSE)

        # ----- album pass (unchanged) -----
        album_names = sorted({clean_text(x) for x in df["album"] if clean_text(x)})
        album_rows = []
        for j, album in enumerate(album_names, 1):
            row = {"spotify_release_name": album, "lastfm_album_name": None,
                   "lastfm_album_listeners": None, "lastfm_album_playcount": None,
                   "lastfm_album_match_status": "error_or_not_found"}
            if album == "Trilogy (bonus)":
                row["lastfm_album_match_status"] = "skipped_synthetic_label"
                album_rows.append(row); continue
            try:
                d = call(session, api_key, "album.getInfo",
                         artist="The Weeknd", album=album, autocorrect=1)
                a = d.get("album", {})
                row.update({
                    "lastfm_album_name": a.get("name"),
                    "lastfm_album_listeners": a.get("listeners"),
                    "lastfm_album_playcount": a.get("playcount"),
                    "lastfm_album_match_status": "matched" if a else "empty_response",
                })
            except Exception as exc:
                log_rows.append({"kind": "album", "title": album, "artist": "The Weeknd",
                                 "error": safe_err(exc)})
            album_rows.append(row)
            if j % 15 == 0 or j == len(album_names):
                print(f"  albums {j}/{len(album_names)}")
            time.sleep(PAUSE)

    # ----- write outputs -----
    agg_rows = []
    for (title, sa), stats in agg.items():
        agg_rows.append({"track": title, "_artist_set_key": "|".join(sorted(sa)), **stats})
    agg_df = pd.DataFrame(agg_rows)

    df["_artist_set_key"] = df["_spotify_artists"].map(lambda s: "|".join(sorted(s)))
    merged = df.merge(agg_df, on=["track", "_artist_set_key"],
                      how="left", validate="many_to_one")
    merged = merged.drop(columns=["_title", "_spotify_artists",
                                  "_first_artist", "_artist_set_key"])
    merged.to_csv(TRACK_OUT, index=False)

    pd.DataFrame(match_rows).to_csv(MATCH_OUT, index=False)
    pd.DataFrame(album_rows).to_csv(ALBUM_OUT, index=False)
    pd.DataFrame(log_rows, columns=["kind", "title", "artist", "error"]).to_csv(
        LOG_OUT, index=False)

    matched = int((merged["lastfm_match_status"] == "matched").sum())
    print(f"\nDone.")
    print(f"Track appearances: {len(merged)}")
    print(f"Matched: {matched}/{len(merged)}")
    print(f"Unique pairs looked up: {len(key_list)}")
    print(f"Saved: {TRACK_OUT.name}, {MATCH_OUT.name}, {ALBUM_OUT.name}, {LOG_OUT.name}")


if __name__ == "__main__":
    main()