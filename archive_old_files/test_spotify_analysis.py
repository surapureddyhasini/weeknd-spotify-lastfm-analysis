"""Offline regression tests for spotify_analysis.py; no API credentials required."""
import pandas as pd
from spotify_analysis import build_clean


def row(album, track, track_id, artists="The Weeknd", release_date="2011-01-01", album_type="album", explicit=False):
    return {
        "album_id": f"album-{album.lower().replace(' ', '-')}",
        "album": album,
        "api_album_type": album_type,
        "release_date": release_date,
        "track_id": track_id,
        "track": track,
        "track_number": 1,
        "disc_number": 1,
        "duration_ms": 180000,
        "duration_min": 3.0,
        "explicit": explicit,
        "artists": artists,
        "n_artists": len(artists.split(", ")),
    }


def run_tests():
    raw = pd.DataFrame([
        row("House of Balloons", "Wicked Games", "hob-1"),
        row("Trilogy", "Wicked Games", "tri-1", release_date="2012-11-13", album_type="compilation"),
        row("Trilogy", "Previously Unreleased Song", "tri-bonus", release_date="2012-11-13", album_type="compilation"),
        # Same title, different credited artist: must not be mistaken for the same recording.
        row("Starboy", "Wicked Games", "different-song", artists="Other Artist", release_date="2016-11-25"),
        # Same ISRC on two different Spotify IDs should resolve to one catalogue recording.
        row("After Hours", "Blinding Lights", "bl-1", release_date="2020-03-20"),
        row("Blinding Lights - Single", "Blinding Lights", "bl-2", release_date="2019-11-29", album_type="single"),
    ])
    clean = build_clean(raw, {"bl-1": "USUG11904206", "bl-2": "USUG11904206"})

    tri_duplicate = clean[(clean["album"] == "Trilogy") & (clean["track"] == "Wicked Games")].iloc[0]
    assert bool(tri_duplicate["is_duplicate_of_other_release"])
    assert not bool(tri_duplicate["in_default_view"])

    bonus = clean[clean["album"] == "Trilogy (bonus)"]
    assert len(bonus) == 1
    assert bool(bonus.iloc[0]["in_default_view"])
    assert bonus.iloc[0]["era"] == "Mixtape era"

    same_title_other_artist = clean[clean["track_id"] == "different-song"].iloc[0]
    assert not bool(same_title_other_artist["is_duplicate_of_other_release"])

    same_isrc_rows = clean[clean["isrc"] == "USUG11904206"]
    assert len(same_isrc_rows) == 2
    assert int(same_isrc_rows["is_primary_track"].sum()) == 1
    assert int(same_isrc_rows["count_in_catalogue"].sum()) == 1
    print("All offline Spotify data-cleaning tests passed.")


if __name__ == "__main__":
    run_tests()
