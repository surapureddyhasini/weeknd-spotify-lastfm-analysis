import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ==========================================
# 1. PAGE CONFIG & CUSTOM CSS
# ==========================================
st.set_page_config(page_title="The Weeknd | Data Analysis", layout="wide", initial_sidebar_state="expanded")

# Custom CSS to make it look premium
st.markdown("""
<style>
    /* Main background */
    .stApp {
        background-color: #0E1117;
    }
    
    /* Hide default Streamlit headers */
    header {visibility: hidden;}
    
    /* Custom Title Styling */
    h1 {
        font-family: 'Helvetica Neue', sans-serif;
        font-weight: 800;
        letter-spacing: -1px;
        color: #FFFFFF;
        text-align: center;
        margin-bottom: 0px;
    }
    h2 {
        font-family: 'Helvetica Neue', sans-serif;
        font-weight: 600;
        color: #A0AAB5;
        text-align: center;
        font-size: 1.2rem !important;
        margin-top: 0px;
        margin-bottom: 40px;
    }
    h3 {
        font-weight: 600;
        color: #FFFFFF;
        padding-bottom: 10px;
        border-bottom: 1px solid #30363D;
        margin-top: 20px;
    }
    
    /* Style the KPI metric cards */
    [data-testid="stMetric"] {
        background-color: #161B22;
        border: 1px solid #30363D;
        border-radius: 12px;
        padding: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background-color: #0E1117;
        border-right: 1px solid #30363D;
    }
    
    /* Chart container styling (Glassmorphism effect) */
    .stPlotlyChart {
        background-color: #161B22;
        border-radius: 12px;
        padding: 10px;
        border: 1px solid #30363D;
        box-shadow: 0 4px 6px rgba(0,0,0,0.2);
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. LOAD DATA
# ==========================================
@st.cache_data
def load_data():
    df = pd.read_csv("weeknd_analysis_ready.csv")
    albums = pd.read_csv("weeknd_album_summary.csv")
    return df, albums

df, album_summary = load_data()

# Global chart layout templates
CHART_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(0,0,0,0)',
    font=dict(family="Helvetica Neue, sans-serif", color="#A0AAB5"),
    margin=dict(l=20, r=20, t=40, b=20)
)

# ==========================================
# 3. SIDEBAR FILTERS
# ==========================================
with st.sidebar:
    st.markdown("### ⚙️ Dashboard Controls")
    st.markdown("---")
    
    view_mode = st.radio("Dataset", ["Studio Albums Only", "All Releases"])
    
    st.markdown("##### Filtration")
    exclude_remixes = st.checkbox("Exclude Remixes/Acapellas", value=True)
    exclude_live = st.checkbox("Exclude Live Tracks", value=True)
    
    st.markdown("---")
    st.markdown("##### Time Period")
    all_eras = sorted(df["era"].dropna().unique())
    selected_eras = st.multiselect("Select Eras", all_eras, default=all_eras)

# Apply Filters
base_df = df.copy()
if view_mode == "Studio Albums Only":
    base_df = base_df[~base_df["album"].str.startswith("Single:")]
if exclude_remixes:
    base_df = base_df[~base_df["track"].str.contains("Remix|A Cappella|Remix", case=False, na=False)]
if exclude_live:
    base_df = base_df[~base_df["is_live"]]
base_df = base_df[base_df["era"].isin(selected_eras)]

clean = base_df[(base_df["in_default_view"] == True) & (base_df["is_primary_track"] == True) & (~base_df["is_interlude"])]

# ==========================================
# 4. HEADER & KPI CARDS
# ==========================================
st.markdown("<h1>The Weeknd</h1>", unsafe_allow_html=True)
st.markdown("<h2>A Data-Driven Career Retrospective</h2>", unsafe_allow_html=True)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Unique Tracks", f"{len(clean):,}")
with col2:
    st.metric("Total Plays", f"{clean['lastfm_track_playcount'].sum():,.0f}")
with col3:
    st.metric("Total Listeners", f"{clean['lastfm_track_listeners'].sum():,.0f}")
with col4:
    if not clean.empty:
        top_track = clean.nlargest(1, "lastfm_track_playcount").iloc[0]
        st.metric("Most Played", top_track["track"], f"{top_track['lastfm_track_playcount']:,.0f} plays")

st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# 5. CHART SECTIONS (Scrolling Layout)
# ==========================================

# --- SECTION 1: POPULARITY ---
st.markdown("### 🏆 Popularity & Hits")
col1, col2 = st.columns(2)

with col1:
    st.markdown("**How do we define popularity?**")
    top_n = st.slider("Select Top N songs", 5, 15, 10)
    top_plays = clean.nlargest(top_n, "lastfm_track_playcount")
    
    fig_q1 = px.bar(
        top_plays, x="lastfm_track_playcount", y="track", orientation='h',
        color="lastfm_track_playcount", color_continuous_scale="Purples"
    )
    fig_q1.update_layout(**CHART_LAYOUT, yaxis={'categoryorder':'total ascending'}, showlegend=False, coloraxis_showscale=False)
    fig_q1.update_yaxes(title=None)
    fig_q1.update_xaxes(title="Total Plays")
    st.plotly_chart(fig_q1, use_container_width=True)

with col2:
    st.markdown("**The #1 Hit from Each Album**")
    if view_mode == "Studio Albums Only":
        studio = album_summary[~album_summary["canonical_album"].str.startswith("Single:")].sort_values("total_playcount", ascending=True)
    else:
        studio = album_summary.sort_values("total_playcount", ascending=True)
        
    fig_q11 = px.bar(
        studio, x="top_track_playcount", y="canonical_album", text="top_track", orientation='h',
        color="total_playcount", color_continuous_scale="Blues"
    )
    fig_q11.update_layout(**CHART_LAYOUT, coloraxis_showscale=False)
    fig_q11.update_traces(textposition='inside')
    fig_q11.update_yaxes(title=None)
    fig_q11.update_xaxes(title="Playcount of Top Track")
    st.plotly_chart(fig_q11, use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- SECTION 2: THE SHAPE OF LISTENING ---
st.markdown("### 📈 The Shape of Listening")
col3, col4 = st.columns(2)

with col3:
    st.markdown("**Hits vs Deep Cuts (Are albums front-loaded?)**")
    # Filter studio for Q3 to exclude singles (fixes the 100% bug)
    q3_data = studio[studio["n_primary_tracks"] > 3] 
    
    fig_q3 = px.scatter(
        q3_data, x="total_playcount", y="top3_share_pct", size="total_playcount", 
        color="era", hover_name="canonical_album", color_discrete_sequence=px.colors.qualitative.Pastel
    )
    fig_q3.update_layout(**CHART_LAYOUT)
    fig_q3.update_xaxes(title="Total Album Plays")
    fig_q3.update_yaxes(title="Top 3 Tracks Share (%)")
    st.plotly_chart(fig_q3, use_container_width=True)

with col4:
    st.markdown("**Streamed vs Replayed (Reach vs Depth)**")
    fig_q5 = px.scatter(
        clean, x="lastfm_track_listeners", y="lastfm_track_playcount", 
        color="era", hover_name="track", size="lastfm_track_playcount",
        color_discrete_sequence=px.colors.qualitative.Pastel
    )
    fig_q5.update_layout(**CHART_LAYOUT)
    fig_q5.update_xaxes(title="Unique Listeners")
    fig_q5.update_yaxes(title="Total Playcount")
    st.plotly_chart(fig_q5, use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- SECTION 3: DEEP DIVE ---
st.markdown("### 🎛️ Deep Dive")
col5, col6, col7 = st.columns(3)

with col5:
    st.markdown("**Catalogue Distribution**")
    fig_q10 = px.histogram(clean, x="lastfm_track_playcount", nbins=40, color_discrete_sequence=['#8B5CF6'])
    fig_q10.update_layout(**CHART_LAYOUT)
    fig_q10.update_xaxes(title="Total Playcount")
    fig_q10.update_yaxes(title="Number of Tracks")
    st.plotly_chart(fig_q10, use_container_width=True)

with col6:
    st.markdown("**Solo vs Collabs**")
    collab_stats = clean.groupby("is_collab")["lastfm_track_playcount"].median().reset_index()
    collab_stats["Type"] = collab_stats["is_collab"].map({True: "Collab", False: "Solo"})
    fig_q4 = px.bar(collab_stats, x="Type", y="lastfm_track_playcount", color="Type", color_discrete_sequence=['#F59E0B', '#3B82F6'])
    fig_q4.update_layout(**CHART_LAYOUT, showlegend=False)
    fig_q4.update_xaxes(title=None)
    fig_q4.update_yaxes(title="Median Playcount")
    st.plotly_chart(fig_q4, use_container_width=True)

with col7:
    st.markdown("**Explicit vs Clean**")
    explicit_stats = clean.groupby("explicit")["lastfm_track_playcount"].median().reset_index()
    explicit_stats["Type"] = explicit_stats["explicit"].map({True: "Explicit", False: "Clean"})
    fig_q9 = px.bar(explicit_stats, x="Type", y="lastfm_track_playcount", color="Type", color_discrete_sequence=['#EF4444', '#10B981'])
    fig_q9.update_layout(**CHART_LAYOUT, showlegend=False)
    fig_q9.update_xaxes(title=None)
    fig_q9.update_yaxes(title="Median Playcount")
    st.plotly_chart(fig_q9, use_container_width=True)