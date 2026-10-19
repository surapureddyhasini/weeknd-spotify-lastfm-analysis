"""Build the analysis-ready table from the audited Spotify catalogue
and the corrected Last.fm stats (v5).

Outputs:
  - weeknd_analysis_ready.csv         all 376 rows, enriched
  - weeknd_album_summary.csv          one row per canonical album
  - weeknd_collaborator_summary.csv   one row per collaborator
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

AUDITED = Path("weeknd_tracks_audited_final.csv")
LASTFM = Path("weeknd_lastfm_track_stats_v5.csv")
OUT_TRACKS = Path("weeknd_analysis_ready.csv")
OUT_ALBUMS = Path("weeknd_album_summary.csv")
OUT_COLLABS = Path("weeknd_collaborator_summary.csv")

CURRENT_YEAR = 2026

# ---------------------------------------------------------------- canonical albums
# Folds deluxe/alternate editions into their base release so album-level
# aggregation counts each recording once.
CANONICAL_ALBUM_MAP: dict[str, str] = {
    "House Of Balloons (Original)": "House of Balloons",
    "Thursday (Original)": "Thursday",
    "Echoes Of Silence (Original)": "Echoes of Silence",
    "Trilogy": "Trilogy",
    "Trilogy (bonus)": "Trilogy",
    "Kiss Land": "Kiss Land",
    "Kiss Land (Deluxe)": "Kiss Land",
    "Beauty Behind The Madness": "Beauty Behind the Madness",
    "Starboy": "Starboy",
    "Starboy (Deluxe)": "Starboy",
    "My Dear Melancholy,": "My Dear Melancholy,",
    "After Hours": "After Hours",
    "After Hours (Deluxe)": "After Hours",
    "Dawn FM": "Dawn FM",
    "Dawn FM (Alternate World)": "Dawn FM",
    "Hurry Up Tomorrow": "Hurry Up Tomorrow",
    "Live At SoFi Stadium": "Live at SoFi Stadium",
}

# Non-album release titles (singles) get a canonical label that groups them
# under the era they belong to but doesn't merge them into a studio album.
SINGLE_CANONICAL_PREFIX = "Single: "


def canonical_album(album: str, release_type: str) -> str:
    a = str(album).strip()
    if a in CANONICAL_ALBUM_MAP:
        return CANONICAL_ALBUM_MAP[a]
    if release_type == "Single":
        return SINGLE_CANONICAL_PREFIX + a
    return a


# ---------------------------------------------------------------- text helpers
_REMIX_PAT = re.compile(r"\bremix\b", re.IGNORECASE)
_LIVE_PAT = re.compile(r"\blive\b", re.IGNORECASE)
_INTERLUDE_PAT = re.compile(r"\b(interlude|skit)\b", re.IGNORECASE)


def is_remix(title: str) -> bool:
    return bool(_REMIX_PAT.search(str(title)))


def is_live(title: str) -> bool:
    return bool(_LIVE_PAT.search(str(title)))


def is_interlude(title: str, duration_ms: float) -> bool:
    if pd.notna(duration_ms) and float(duration_ms) < 60_000:
        return True
    return bool(_INTERLUDE_PAT.search(str(title)))


# ---------------------------------------------------------------- main
def main():
    if not AUDITED.exists():
        raise SystemExit(f"Missing {AUDITED}")
    if not LASTFM.exists():
        raise SystemExit(f"Missing {LASTFM}")

    # ---- load & join ----
    audited = pd.read_csv(AUDITED)
    lastfm = pd.read_csv(LASTFM)

    # Last.fm file is 1 row per release-appearance already. Join on track_id.
    cols_keep = [
        "track_id",
        "lastfm_match_count",
        "lastfm_track_listeners",
        "lastfm_track_playcount",
        "lastfm_match_status",
        "lastfm_top_match_name",
        "lastfm_top_match_artist",
    ]
    lastfm_slim = lastfm[cols_keep].drop_duplicates(subset="track_id")
    df = audited.merge(lastfm_slim, on="track_id", how="left")

    # ---- derived columns ----
    df["canonical_album"] = df.apply(
        lambda r: canonical_album(r["album"], r["release_type"]), axis=1)
    df["is_remix"] = df["track"].apply(is_remix)
    df["is_live"] = df["track"].apply(is_live)
    df["is_interlude"] = df.apply(
        lambda r: is_interlude(r["track"], r.get("duration_ms")), axis=1)
    df["title_length_chars"] = df["track"].astype(str).str.len()

    # Sanitize numeric Last.fm columns.
    for c in ("lastfm_track_listeners", "lastfm_track_playcount"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["replay_factor"] = (df["lastfm_track_playcount"]
                           / df["lastfm_track_listeners"]).round(2)
    df["plays_per_minute"] = (df["lastfm_track_playcount"]
                              / df["duration_min"]).round(0)
    df["estimated_minutes_listened"] = (
        df["lastfm_track_playcount"] * df["duration_min"]).round(0)
    df["years_since_release"] = (
        CURRENT_YEAR - df["year"]).clip(lower=1)
    df["listeners_per_year"] = (
        df["lastfm_track_listeners"] / df["years_since_release"]).round(0)

    # Album position within canonical album (using primary tracks only so
    # deluxe-bonus tracks don't distort position on the base release).
    df["album_position"] = pd.NA
    df["album_position_pct"] = pd.NA
    mask_for_pos = (df["in_default_view"] & ~df["is_remix"] & ~df["is_live"])
    for alb in df.loc[mask_for_pos, "canonical_album"].unique():
        subset_idx = df.index[(df["canonical_album"] == alb) & mask_for_pos]
        ordered = df.loc[subset_idx].sort_values(
            ["disc_number", "track_number"]).index
        n = len(ordered)
        for pos, idx in enumerate(ordered, start=1):
            df.at[idx, "album_position"] = pos
            df.at[idx, "album_position_pct"] = round(pos / n * 100, 1)

    # ---- write the main analysis-ready file ----
    df.to_csv(OUT_TRACKS, index=False)
    print(f"Wrote {OUT_TRACKS.name}  ({len(df)} rows, {len(df.columns)} cols)")

    # ---- album summary ----
    # Use only default-view, primary, non-remix, non-live tracks per album.
    alb_scope = df[
        df["in_default_view"] & ~df["is_remix"] & ~df["is_live"]
    ].copy()

    agg_rows = []
    for alb, g in alb_scope.groupby("canonical_album"):
        plays = g["lastfm_track_playcount"].dropna()
        listeners = g["lastfm_track_listeners"].dropna()
        total_plays = float(plays.sum()) if not plays.empty else 0.0
        total_listeners = float(listeners.sum()) if not listeners.empty else 0.0
        n = len(g)

        top_row = g.sort_values("lastfm_track_playcount",
                                ascending=False).iloc[0] if n else None
        top_track = top_row["track"] if top_row is not None else None
        top_plays = (float(top_row["lastfm_track_playcount"])
                     if top_row is not None and pd.notna(top_row["lastfm_track_playcount"])
                     else None)
        top_share = round(top_plays / total_plays * 100, 1) \
            if top_plays and total_plays else None

        # top-3 share (hits vs deep cuts)
        top3_plays = plays.sort_values(ascending=False).head(3).sum()
        top3_share = round(top3_plays / total_plays * 100, 1) \
            if total_plays else None

        agg_rows.append({
            "canonical_album": alb,
            "era": g["era"].mode().iloc[0] if not g["era"].mode().empty else None,
            "release_year": int(g["year"].dropna().min())
            if g["year"].notna().any() else None,
            "n_primary_tracks": n,
            "total_playcount": total_plays,
            "total_listeners": total_listeners,
            "avg_playcount_per_track": round(total_plays / n, 0) if n else None,
            "median_playcount": float(plays.median()) if not plays.empty else None,
            "top_track": top_track,
            "top_track_playcount": top_plays,
            "top_track_share_pct": top_share,
            "top3_share_pct": top3_share,
            "total_runtime_min": round(g["duration_min"].sum(), 1),
            "n_explicit": int(g["explicit"].sum()),
            "n_collabs": int(g["is_collab"].sum()),
        })

    album_summary = pd.DataFrame(agg_rows).sort_values(
        "total_playcount", ascending=False)
    album_summary.to_csv(OUT_ALBUMS, index=False)
    print(f"Wrote {OUT_ALBUMS.name}  ({len(album_summary)} albums)")

    # ---- collaborator summary ----
    collab_scope = df[
        df["in_default_view"] & df["is_collab"]
    ].copy()

    # Expand comma-separated collaborators into one row per (track, collaborator).
    rows = []
    for _, r in collab_scope.iterrows():
        for c in str(r["collaborators"]).split(","):
            c = c.strip()
            if c:
                rows.append({
                    "collaborator": c,
                    "track": r["track"],
                    "lastfm_track_playcount": r["lastfm_track_playcount"],
                    "lastfm_track_listeners": r["lastfm_track_listeners"],
                })
    collab_long = pd.DataFrame(rows)
    if not collab_long.empty:
        collab_summary = collab_long.groupby("collaborator").agg(
            n_tracks=("track", "nunique"),
            avg_playcount=("lastfm_track_playcount", "mean"),
            total_playcount=("lastfm_track_playcount", "sum"),
            avg_listeners=("lastfm_track_listeners", "mean"),
        ).reset_index()
        # top track per collaborator
        top_tracks = (
            collab_long.sort_values("lastfm_track_playcount", ascending=False)
            .drop_duplicates("collaborator")[["collaborator", "track"]]
            .rename(columns={"track": "top_track"})
        )
        collab_summary = collab_summary.merge(top_tracks, on="collaborator")
        collab_summary = collab_summary.sort_values(
            "n_tracks", ascending=False)
        collab_summary.to_csv(OUT_COLLABS, index=False)
        print(f"Wrote {OUT_COLLABS.name}  ({len(collab_summary)} collaborators)")
    else:
        print("No collaborators found — skipping collaborator summary.")

    # ---- quick sanity ----
    print("\n--- Sanity ---")
    checks = [
        "Blinding Lights", "Starboy", "Wicked Games",
        "Save Your Tears", "I Was Never There",
    ]
    cols = ["track", "lastfm_track_playcount", "lastfm_track_listeners",
            "replay_factor", "canonical_album", "is_interlude"]
    print(df.loc[df["track"].isin(checks), cols].to_string(index=False))


if __name__ == "__main__":
    main()