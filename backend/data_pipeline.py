import requests
from bs4 import BeautifulSoup, Comment
import pandas as pd
import os
import time
from functools import reduce

# --- Configuration ---
BASE_URL = "https://fbref.com"
OUTPUT_DIR = "fpl_data"
PLAYER_STATS_FILE = os.path.join(OUTPUT_DIR, "fbref_player_stats.csv")

# URLs for different player statistic tables on FBref
STAT_URLS = {
    "standard": "/en/comps/9/stats/Premier-League-Stats",
    "shooting": "/en/comps/9/shooting/Premier-League-Stats",
    "passing": "/en/comps/9/passing/Premier-League-Stats",
    "defense": "/en/comps/9/defense/Premier-League-Stats",
    "possession": "/en/comps/9/possession/Premier-League-Stats",
    "gca": "/en/comps/9/gca/Premier-League-Stats", # Goal and Shot Creation
}

# Headers to mimic a browser request
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def clean_player_name(df):
    """Removes special characters from player names."""
    if 'Player' in df.columns:
        df['Player'] = df['Player'].str.split('\\').str[0].str.strip()
    return df

def fetch_stats_table(stat_type: str, url_suffix: str) -> pd.DataFrame | None:
    """Fetches and parses a statistics table from an FBref URL, handling commented-out HTML."""
    try:
        full_url = BASE_URL + url_suffix
        print(f"Fetching {stat_type} stats from {full_url}...")
        
        response = requests.get(full_url, headers=HEADERS)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')

        table_id = f"stats_{stat_type}"
        
        # --- THIS IS THE CORRECTED LINE ---
        # The placeholder div ID is "all_..." not "div_..."
        placeholder = soup.find('div', {'id': f'all_{table_id}'})
        
        if not placeholder:
            print(f"❌ No placeholder div found for {table_id}")
            return None

        comment = placeholder.find(string=lambda text: isinstance(text, Comment))
        if not comment:
            print(f"❌ No comment found for {table_id}. The table might be directly visible.")
            table_html_str = str(placeholder.find('table', {'id': table_id}))
        else:
            comment_soup = BeautifulSoup(comment, 'lxml')
            table_html_str = str(comment_soup.find('table', {'id': table_id}))

        if 'None' in table_html_str:
            print(f"❌ Could not extract table HTML for {table_id}")
            return None
            
        df = pd.read_html(table_html_str, header=1)[0]
        
        df = df[df['Rk'].notna() & (df['Rk'] != 'Rk')]
        df = df.drop(columns=['Rk', 'Matches'], errors='ignore')
        df = clean_player_name(df)
        
        key_cols = ['Player', 'Nation', 'Pos', 'Squad', 'Age', 'Born', '90s']
        df = df.rename(columns={c: f"{c}_{stat_type}" for c in df.columns if c not in key_cols})

        print(f"✅ Successfully fetched and processed {stat_type} stats.")
        return df
        
    except Exception as e:
        print(f"❌ Error fetching {stat_type} stats: {e}")
        return None

def run_data_pipeline():
    """Main function to scrape all data, merge it, and save to a single file."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    all_dfs = []
    for stat_type, url_suffix in STAT_URLS.items():
        df = fetch_stats_table(stat_type, url_suffix)
        if df is not None:
            all_dfs.append(df)
        time.sleep(3)

    if not all_dfs:
        print("🚨 No dataframes were fetched. Exiting pipeline.")
        return

    print("\nMerging all player dataframes...")
    merged_df = reduce(lambda left, right: pd.merge(left, right, on=['Player', 'Nation', 'Pos', 'Squad', 'Age', 'Born', '90s'], how='outer'), all_dfs)
    
    for col in merged_df.columns:
        if pd.api.types.is_numeric_dtype(merged_df[col]):
            merged_df[col] = merged_df[col].fillna(0)
    
    merged_df.to_csv(PLAYER_STATS_FILE, index=False)
    print(f"\n✅ Data pipeline complete. All player stats saved to '{PLAYER_STATS_FILE}'.")
    
if __name__ == "__main__":
    run_data_pipeline()