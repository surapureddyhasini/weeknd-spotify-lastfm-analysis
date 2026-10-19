import pandas as pd
import plotly.express as px
from pathlib import Path

# --- Setup ---
CHARTS_DIR = Path("charts")
CHARTS_DIR.mkdir(exist_ok=True)

# Read data
df = pd.read_csv("weeknd_analysis_ready.csv")
# Base filter: default view, primary tracks, no remixes/lives/interludes
clean = df[
    (df["in_default_view"] == True) & 
    (df["is_primary_track"] == True) & 
    (~df["is_remix"]) & 
    (~df["is_live"]) & 
    (~df["is_interlude"])
]

print("Generating Batch 2 Charts...")

# ---------------------------------------------------------
# Q5: Streamed vs Replayed (Playcount vs Listeners)
# ---------------------------------------------------------
fig_q5 = px.scatter(
    clean,
    x="lastfm_track_listeners",
    y="lastfm_track_playcount",
    color="era",
    hover_name="track",
    size="lastfm_track_playcount",
    title="Q5: Most Streamed vs Most Replayed",
    labels={
        "lastfm_track_listeners": "Unique Listeners",
        "lastfm_track_playcount": "Total Playcount",
        "era": "Era"
    }
)
# Add a line of best fit to show the average replay ratio
fig_q5.update_traces(marker=dict(opacity=0.7, line=dict(width=1, color='DarkSlateGrey')))
fig_q5.write_html(CHARTS_DIR / "Q05_streamed_vs_replayed.html")
print("  -> Saved Q05_streamed_vs_replayed.html")

# ---------------------------------------------------------
# Q7: Track Length vs Plays
# ---------------------------------------------------------
fig_q7 = px.scatter(
    clean,
    x="duration_min",
    y="lastfm_track_playcount",
    color="era",
    hover_name="track",
    trendline="ols", # Ordinary Least Squares regression line
    title="Q7: Track Length vs. Playcount",
    labels={
        "duration_min": "Duration (Minutes)",
        "lastfm_track_playcount": "Total Playcount",
        "era": "Era"
    }
)
fig_q7.update_traces(marker=dict(opacity=0.7))
fig_q7.write_html(CHARTS_DIR / "Q07_length_vs_plays.html")
print("  -> Saved Q07_length_vs_plays.html")

# ---------------------------------------------------------
# Q8: Album Position vs Plays
# ---------------------------------------------------------
# Filter out tracks that don't have an album position (singles)
album_tracks = clean[clean["album_position"].notna()].copy()
album_tracks["album_position"] = album_tracks["album_position"].astype(int)

fig_q8 = px.box(
    album_tracks,
    x="album_position",
    y="lastfm_track_playcount",
    title="Q8: Album Position vs. Playcount (Do people skip to track 1?)",
    labels={
        "album_position": "Track Number on Album",
        "lastfm_track_playcount": "Total Playcount"
    },
    points="all" # Show every track as a dot
)
fig_q8.write_html(CHARTS_DIR / "Q08_album_position.html")
print("  -> Saved Q08_album_position.html")

# ---------------------------------------------------------
# Q10: Catalogue Distribution (The Long Tail)
# ---------------------------------------------------------
fig_q10 = px.histogram(
    clean,
    x="lastfm_track_playcount",
    nbins=50,
    title="Q10: Catalogue Distribution (The Power Law of Streaming)",
    labels={"lastfm_track_playcount": "Total Playcount", "count": "Number of Tracks"},
    color_discrete_sequence=['#636EFA']
)
fig_q10.update_layout(yaxis_title="Number of Tracks")
fig_q10.write_html(CHARTS_DIR / "Q10_catalogue_distribution.html")
print("  -> Saved Q10_catalogue_distribution.html")

print("\nBatch 2 Complete! Open the 'charts' folder to view the new HTML files.")