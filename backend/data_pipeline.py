import httpx
import json
import os
from pathlib import Path
import pandas as pd
import faiss 
from sentence_transformers import SentenceTransformer
import numpy as np # --- FIX: Import the numpy library ---

# --- Configuration ---
SEASONS = ["2021-22", "2022-23", "2023-24"] 
DATA_URL_TEMPLATE = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/{season}/gws/merged_gw.csv"
OUTPUT_DIR = Path(__file__).parent / "fpl_data"
PROCESSED_DATA_PATH = OUTPUT_DIR / "processed_player_data.json"
FAISS_INDEX_PATH = OUTPUT_DIR / "player_data.index"

# --- Main Functions ---

def download_data():
    print("--- Starting Historical Data Download ---")
    OUTPUT_DIR.mkdir(exist_ok=True)
    with httpx.Client() as client:
        for season in SEASONS:
            url = DATA_URL_TEMPLATE.format(season=season)
            output_path = OUTPUT_DIR / f"data_{season}.csv"
            if output_path.exists():
                print(f"Data for season {season} already exists. Skipping download.")
                continue
            print(f"Downloading data for season {season}...")
            try:
                response = client.get(url, timeout=30.0)
                response.raise_for_status()
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(response.text)
                print(f"✅ Successfully saved data for season {season}")
            except Exception as e:
                print(f"❌ Error downloading data for season {season}: {e}")

def process_data():
    print("\n--- Starting Data Processing ---")
    all_player_data = {}
    for season in SEASONS:
        file_path = OUTPUT_DIR / f"data_{season}.csv"
        if not file_path.exists():
            print(f"⚠️  Warning: Data file for season {season} not found.")
            continue
        print(f"Processing data for season {season}...")
        df = pd.read_csv(file_path)
        
        # Get the final value for each player in the season
        df['value'] = df['value'] / 10.0
        final_values = df.loc[df.groupby('name')['GW'].idxmax()][['name', 'value']]
        
        player_season_stats = df.groupby('name').agg(
            total_points=('total_points', 'sum'),
            goals_scored=('goals_scored', 'sum'),
            assists=('assists', 'sum'),
            minutes=('minutes', 'sum')
        ).reset_index()

        # Merge with final values
        player_season_stats = pd.merge(player_season_stats, final_values, on='name', how='left')

        for _, row in player_season_stats.iterrows():
            player_name = row['name']
            if player_name not in all_player_data:
                all_player_data[player_name] = {}
            
            all_player_data[player_name][season] = {
                'cost': round(row['value'], 1),
                'total_points': int(row['total_points']),
                'goals_scored': int(row['goals_scored']),
                'assists': int(row['assists']),
                'minutes_played': int(row['minutes'])
            }
    with open(PROCESSED_DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(all_player_data, f, indent=2)
    print(f"✅ Successfully processed and saved player data to {PROCESSED_DATA_PATH}")

def create_vector_store():
    print("\n--- Creating Vector Store (This may take a few minutes) ---")
    if not PROCESSED_DATA_PATH.exists():
        print("❌ Processed data file not found. Please run process_data() first.")
        return

    with open(PROCESSED_DATA_PATH, 'r', encoding='utf-8') as f:
        player_data = json.load(f)

    print("Loading sentence transformer model...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    player_names = list(player_data.keys())
    player_descriptions = []
    for name, seasons in player_data.items():
        desc = f"Player: {name}. "
        for season, stats in seasons.items():
            desc += (f"In {season}, they cost around £{stats.get('cost', 'N/A')}m, "
                     f"scored {stats['total_points']} points, "
                     f"and played {stats['minutes_played']} minutes. ")
        player_descriptions.append(desc)
    
    print(f"Creating embeddings for {len(player_names)} players...")
    embeddings = model.encode(player_descriptions, show_progress_bar=True)

    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index = faiss.IndexIDMap(index)
    
    ids = np.array(range(len(player_names)))
    index.add_with_ids(embeddings, ids)

    faiss.write_index(index, str(FAISS_INDEX_PATH))
    print(f"✅ Vector store created and saved to {FAISS_INDEX_PATH}")


if __name__ == "__main__":
    download_data()
    process_data()
    create_vector_store()
