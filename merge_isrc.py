import pandas as pd

# 1. Load the two files
# The main file (without ISRC)
ready = pd.read_csv("weeknd_analysis_ready.csv")
# The new file (with ISRC)
with_isrc = pd.read_csv("weeknd_tracks_audited_final_with_isrc.csv")

# 2. Map the ISRCs based on the unique Spotify Track ID
isrc_map = dict(zip(with_isrc["track_id"], with_isrc["isrc"]))

# 3. Add the ISRC column to the main file
ready["isrc"] = ready["track_id"].map(isrc_map)

# 4. Save it back out (preserving your original just in case)
ready.to_csv("weeknd_analysis_ready.csv", index=False)

# 5. Quick check
print(f"Total rows: {len(ready)}")
print(f"Rows with ISRC: {ready['isrc'].notna().sum()}")
print("Successfully added ISRCs to weeknd_analysis_ready.csv")