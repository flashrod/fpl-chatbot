import httpx
import json
from pathlib import Path
import pandas as pd
import faiss 
from sentence_transformers import SentenceTransformer
import numpy as np
import asyncio
import sportsdb_service # Import our new service

# --- SEASON UPDATE ---
# Update to the latest three completed seasons
SEASONS = ["2022-23", "2023-24", "2024-25"] 
DATA_URL_TEMPLATE = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/{season}/gws/merged_gw.csv"
OUTPUT_DIR = Path(__file__).parent / "fpl_data"
PROCESSED_DATA_PATH = OUTPUT_DIR / "processed_player_data.json"
FAISS_INDEX_PATH = OUTPUT_DIR / "player_data.index"

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
        try:
            df = pd.read_csv(file_path, on_bad_lines='skip')
        except Exception as e:
            print(f"❌ Could not process {file_path} due to an error: {e}")
            continue
        
        df['value'] = df['value'] / 10.0
        final_values = df.loc[df.groupby('name')['GW'].idxmax()][['name', 'value']]
        
        player_season_stats = df.groupby('name').agg(
            total_points=('total_points', 'sum'),
            goals_scored=('goals_scored', 'sum'),
            assists=('assists', 'sum'),
            minutes=('minutes', 'sum')
        ).reset_index()

        player_season_stats = pd.merge(player_season_stats, final_values, on='name', how='left')

        for _, row in player_season_stats.iterrows():
            player_name = row['name']
            if player_name not in all_player_data:
                all_player_data[player_name] = {}
            
            all_player_data[player_name][season] = {
                'cost': round(row['value'], 1) if pd.notna(row['value']) else 0,
                'total_points': int(row['total_points']),
                'goals_scored': int(row['goals_scored']),
                'assists': int(row['assists']),
                'minutes_played': int(row['minutes'])
            }
    with open(PROCESSED_DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(all_player_data, f, indent=2)
    print(f"✅ Successfully processed and saved player data to {PROCESSED_DATA_PATH}")

async def enrich_with_sportsdb_data():
    """
    Enriches the processed data with details from TheSportsDB.
    """
    print("\n--- Enriching Data with TheSportsDB Details ---")
    if not PROCESSED_DATA_PATH.exists():
        print("❌ Processed data file not found. Please run process_data() first.")
        return

    sportsdb_players = await sportsdb_service.get_all_epl_players()
    if not sportsdb_players:
        print("❌ Failed to fetch data from TheSportsDB. Aborting enrichment.")
        return

    with open(PROCESSED_DATA_PATH, 'r+', encoding='utf-8') as f:
        fpl_player_data = json.load(f)
        
        enriched_count = 0
        for fpl_name in fpl_player_data:
            # Use case-insensitive matching to find the player
            matched_name = next((sdb_name for sdb_name in sportsdb_players if sdb_name.lower() == fpl_name.lower()), None)
            
            if matched_name:
                fpl_player_data[fpl_name]["details"] = sportsdb_players[matched_name]
                enriched_count += 1

        print(f"✅ Enriched {enriched_count} players with details from TheSportsDB.")
        f.seek(0)
        json.dump(fpl_player_data, f, indent=2)
        f.truncate()
    print("✅ Successfully updated data with TheSportsDB details.")

def create_vector_store():
    print("\n--- Creating Vector Store ---")
    if not PROCESSED_DATA_PATH.exists():
        print("❌ Processed data file not found.")
        return
    with open(PROCESSED_DATA_PATH, 'r', encoding='utf-8') as f:
        player_data = json.load(f)
    print("Loading sentence transformer model...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    player_names = list(player_data.keys())
    player_descriptions = []
    for name, data in player_data.items():
        desc = f"Player: {name}. "
        if "details" in data and data["details"].get("description"):
            desc += data["details"]["description"]
        elif "2024-25" in data:
            desc += f"In 2024-25, they scored {data['2024-25'].get('total_points', 'N/A')} points."
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

async def main():
    download_data()
    process_data()
    await enrich_with_sportsdb_data()
    create_vector_store()

if __name__ == "__main__":
    asyncio.run(main())
