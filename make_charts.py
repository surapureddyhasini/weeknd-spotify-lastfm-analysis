import pandas as pd
import plotly.express as px
from pathlib import Path

# --- Setup ---
CHARTS_DIR = Path("charts")
CHARTS_DIR.mkdir(exist_ok=True)

# Read data and apply a basic filter for studio albums (excluding "Single: " prefix)
df = pd.read_csv("weeknd_analysis_ready.csv")
albums = df[
    (df["in_default_view"] == True) & 
    (~df["is_remix"]) & 
    (~df["is_live"]) & 
    (~df["is_interlude"])
]

print("Generating Batch 1 Charts...")

# ---------------------------------------------------------
# Q11: The hit from each album
# ---------------------------------------------------------
album_summary = pd.read_csv("weeknd_album_summary.csv")
# Filter out singles so we only look at actual albums/mixtapes
studio_albums = album_summary[~album_summary["canonical_album"].str.startswith("Single:")]

fig_q11 = px.bar(
    studio_albums.sort_values("total_playcount", ascending=True),
    x="top_track_playcount",
    y="canonical_album",
    text="top_track",
    orientation="h",
    title="Q11: The #1 Hit from Each Album (by Playcount)",
    labels={"top_track_playcount": "Playcount of Top Track", "canonical_album": ""},
    color="total_playcount",
    color_continuous_scale="Blues"
)
fig_q11.update_traces(textposition='inside')
fig_q11.write_html(CHARTS_DIR / "Q11_hit_from_album.html")
print("  -> Saved Q11_hit_from_album.html")

# ---------------------------------------------------------
# Q2: Popularity by era
# ---------------------------------------------------------
era_stats = albums.groupby("era").agg(
    total_playcount=("lastfm_track_playcount", "sum"),
    median_playcount=("lastfm_track_playcount", "median"),
    n_tracks=("track", "count")
).reset_index().sort_values("total_playcount", ascending=False)

fig_q2 = px.bar(
    era_stats,
    x="era",
    y="total_playcount",
    text="n_tracks",
    title="Q2: Total Popularity by Era",
    labels={"total_playcount": "Total Playcount", "era": "Era", "n_tracks": "Tracks"}
)
fig_q2.update_traces(texttemplate='%{text} tracks', textposition='outside')
fig_q2.write_html(CHARTS_DIR / "Q02_era_popularity.html")
print("  -> Saved Q02_era_popularity.html")

# ---------------------------------------------------------
# Q3: Hits vs Deep Cuts (Concentration per album)
# ---------------------------------------------------------
fig_q3 = px.scatter(
    studio_albums,
    x="total_playcount",
    y="top3_share_pct",
    size="total_playcount",
    color="era",
    hover_name="canonical_album",
    title="Q3: Hits vs Deep Cuts (Top 3 tracks' share of total album plays)",
    labels={
        "total_playcount": "Total Album Playcount", 
        "top3_share_pct": "Top 3 Tracks Share (%)",
        "era": "Era"
    }
)
fig_q3.update_traces(marker=dict(line=dict(width=1, color='DarkSlateGrey')))
fig_q3.write_html(CHARTS_DIR / "Q03_hits_vs_deepcuts.html")
print("  -> Saved Q03_hits_vs_deepcuts.html")

# ---------------------------------------------------------
# Q6: Release cadence (Tracks per year)
# ---------------------------------------------------------
cadence = albums[albums["is_primary_track"]].groupby("year").size().reset_index(name="count")

fig_q6 = px.bar(
    cadence,
    x="year",
    y="count",
    title="Q6: Catalogue Growth (Primary Tracks Released per Year)",
    labels={"year": "Year", "count": "Tracks Released"},
    color="count",
    color_continuous_scale="Purples"
)
fig_q6.write_html(CHARTS_DIR / "Q06_release_cadence.html")
print("  -> Saved Q06_release_cadence.html")

# ---------------------------------------------------------
# Q12: Release gaps (Years between studio albums)
# ---------------------------------------------------------
album_years = studio_albums[["canonical_album", "release_year"]].drop_duplicates().sort_values("release_year")
album_years["gap_years"] = album_years["release_year"].diff()

fig_q12 = px.line(
    album_years,
    x="release_year",
    y="gap_years",
    markers=True,
    title="Q12: Release Gaps (Years between Studio Albums)",
    labels={"release_year": "Release Year", "gap_years": "Years Since Previous Album"}
)
fig_q12.update_traces(
    hovertemplate="<b>%{x}</b><br>Gap: %{y} years<extra></extra>"
)
fig_q12.write_html(CHARTS_DIR / "Q12_release_gaps.html")
print("  -> Saved Q12_release_gaps.html")

print("\nBatch 1 Complete! Open the 'charts' folder to view the HTML files.")