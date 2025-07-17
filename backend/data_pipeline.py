import httpx
import json
import os
from pathlib import Path
import pandas as pd

# --- Configuration ---
SEASONS = ["2021-22", "2022-23", "2023-24"] 
DATA_URL_TEMPLATE = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/{season}/gws/merged_gw.csv"
OUTPUT_DIR = Path(__file__).parent / "fpl_data"
PROCESSED_DATA_PATH = OUTPUT_DIR / "processed_player_data.json"

def download_data():
    """
    Downloads historical FPL data for specified seasons and saves it locally.
    """
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
    """
    Processes the downloaded CSV files into a structured JSON knowledge base.
    """
    print("\n--- Starting Data Processing ---")
    all_player_data = {}

    for season in SEASONS:
        file_path = OUTPUT_DIR / f"data_{season}.csv"
        if not file_path.exists():
            print(f"⚠️ Warning: Data file for season {season} not found. Skipping.")
            continue
        
        print(f"Processing data for season {season}...")
        df = pd.read_csv(file_path)

        # Group by player name to aggregate stats for the season
        player_season_stats = df.groupby('name').agg(
            total_points=('total_points', 'sum'),
            goals_scored=('goals_scored', 'sum'),
            assists=('assists', 'sum'),
            minutes=('minutes', 'sum')
        ).reset_index()

        for _, row in player_season_stats.iterrows():
            player_name = row['name']
            if player_name not in all_player_data:
                all_player_data[player_name] = {}
            
            all_player_data[player_name][season] = {
                'total_points': int(row['total_points']),
                'goals_scored': int(row['goals_scored']),
                'assists': int(row['assists']),
                'minutes_played': int(row['minutes'])
            }

    # Save the processed data to a JSON file
    with open(PROCESSED_DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(all_player_data, f, indent=2)
    
    print(f"✅ Successfully processed and saved player data to {PROCESSED_DATA_PATH}")


if __name__ == "__main__":
    download_data()
    process_data()
