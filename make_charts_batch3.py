import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

# --- Setup ---
CHARTS_DIR = Path("charts")
CHARTS_DIR.mkdir(exist_ok=True)

df = pd.read_csv("weeknd_analysis_ready.csv")
clean = df[
    (df["in_default_view"] == True) & 
    (df["is_primary_track"] == True) & 
    (~df["is_remix"]) & 
    (~df["is_live"]) & 
    (~df["is_interlude"])
]

print("Generating Batch 3 Charts & KPIs...")

# ---------------------------------------------------------
# Q1: Three ways to define "Most Popular"
# ---------------------------------------------------------
top_plays = clean.nlargest(10, "lastfm_track_playcount")
top_listeners = clean.nlargest(10, "lastfm_track_listeners")
# Replay factor needs at least 100k listeners to avoid tiny-sample weirdness
replay_clean = clean[clean["lastfm_track_listeners"] > 100000]
top_replay = replay_clean.nlargest(10, "replay_factor")

fig_q1 = go.Figure()
fig_q1.add_trace(go.Bar(y=top_plays["track"], x=top_plays["lastfm_track_playcount"], name="By Total Plays", orientation='h', marker_color='#1f77b4'))
fig_q1.add_trace(go.Bar(y=top_listeners["track"], x=top_listeners["lastfm_track_listeners"], name="By Unique Listeners", orientation='h', marker_color='#ff7f0e', visible=False))
fig_q1.add_trace(go.Bar(y=top_replay["track"], x=top_replay["replay_factor"], name="By Replay Factor", orientation='h', marker_color='#2ca02c', visible=False))

fig_q1.update_layout(
    title="Q1: Three Ways to Define 'Most Popular' (Use buttons to toggle)",
    updatemenus=[dict(
        type="buttons",
        direction="right",
        x=0.7, y=1.15,
        showactive=True,
        buttons=list([
            dict(label="Total Plays", method="update", args=[{"visible": [True, False, False]}]),
            dict(label="Unique Listeners", method="update", args=[{"visible": [False, True, False]}]),
            dict(label="Replay Factor", method="update", args=[{"visible": [False, False, True]}]),
        ]),
    )],
    yaxis=dict(autorange="reversed")
)
fig_q1.write_html(CHARTS_DIR / "Q01_three_definitions.html")
print("  -> Saved Q01_three_definitions.html")

# ---------------------------------------------------------
# Q4: Collabs vs Solo
# ---------------------------------------------------------
collab_stats = clean.groupby("is_collab")["lastfm_track_playcount"].median().reset_index()
collab_stats["Type"] = collab_stats["is_collab"].map({True: "Collaboration", False: "Solo Track"})

fig_q4 = px.bar(
    collab_stats,
    x="Type",
    y="lastfm_track_playcount",
    title="Q4: Solo vs Collaboration (Median Playcount)",
    labels={"lastfm_track_playcount": "Median Playcount", "Type": ""},
    color="Type",
    color_discrete_map={"Collaboration": "#ff7f0e", "Solo Track": "#1f77b4"}
)
fig_q4.write_html(CHARTS_DIR / "Q04_collabs_vs_solo.html")
print("  -> Saved Q04_collabs_vs_solo.html")

# ---------------------------------------------------------
# Q9: Explicit vs Clean
# ---------------------------------------------------------
explicit_stats = clean.groupby("explicit")["lastfm_track_playcount"].median().reset_index()
explicit_stats["Type"] = explicit_stats["explicit"].map({True: "Explicit", False: "Clean"})

fig_q9 = px.bar(
    explicit_stats,
    x="Type",
    y="lastfm_track_playcount",
    title="Q9: Explicit vs Clean (Median Playcount)",
    labels={"lastfm_track_playcount": "Median Playcount", "Type": ""},
    color="Type",
    color_discrete_map={"Explicit": "#d62728", "Clean": "#2ca02c"}
)
fig_q9.write_html(CHARTS_DIR / "Q09_explicit_vs_clean.html")
print("  -> Saved Q09_explicit_vs_clean.html")

# ---------------------------------------------------------
# Q13: Album Runtime Trend
# ---------------------------------------------------------
album_runtimes = pd.read_csv("weeknd_album_summary.csv")
studio_albums = album_runtimes[~album_runtimes["canonical_album"].str.startswith("Single:")].sort_values("release_year")

fig_q13 = px.line(
    studio_albums,
    x="release_year",
    y="total_runtime_min",
    markers=True,
    title="Q13: Album Runtime Trend (Minutes per Album)",
    labels={"release_year": "Release Year", "total_runtime_min": "Total Runtime (Minutes)"}
)
fig_q13.write_html(CHARTS_DIR / "Q13_runtime_trend.html")
print("  -> Saved Q13_runtime_trend.html")

# ---------------------------------------------------------
# KPI CARDS (Summary Text)
# ---------------------------------------------------------
total_tracks = len(clean)
total_plays = clean["lastfm_track_playcount"].sum()
total_listeners = clean["lastfm_track_listeners"].sum()
most_popular = top_plays.iloc[0]["track"]
most_replayed = top_replay.iloc[0]["track"]

# Write a text file with the KPIs so we can read them in Streamlit later
with open("charts/kpi_summary.txt", "w") as f:
    f.write(f"Total Unique Tracks: {total_tracks:,}\n")
    f.write(f"Total Playcount: {total_plays:,.0f}\n")
    f.write(f"Total Listeners: {total_listeners:,.0f}\n")
    f.write(f"Most Popular Song: {most_popular}\n")
    f.write(f"Most Replayed Song: {most_replayed}\n")

print("  -> Saved kpi_summary.txt")
print("\nBatch 3 Complete! All 13 charts are built.")