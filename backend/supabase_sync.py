import os
import httpx
import asyncio
from supabase import create_client, Client
from dotenv import load_dotenv
import logging

# --- Configuration ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

FPL_API_BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_API_FIXTURES = "https://fantasy.premierleague.com/api/fixtures/"

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Supabase URL and Key must be set in your .env file.")

# Headers to mimic a browser request
API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

async def sync_fpl_data_to_supabase():
    """
    Fetches the latest FPL bootstrap and fixtures data and upserts it into a Supabase table.
    """
    logging.info("🚀 Starting FPL data sync to Supabase...")
    
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        async with httpx.AsyncClient(headers=API_HEADERS, timeout=30.0) as client:
            bootstrap_res, fixtures_res = await asyncio.gather(
                client.get(FPL_API_BOOTSTRAP),
                client.get(FPL_API_FIXTURES)
            )
        bootstrap_res.raise_for_status()
        fixtures_res.raise_for_status()

        bootstrap_data = bootstrap_res.json()
        fixtures_data = fixtures_res.json()

        logging.info("✅ Successfully fetched data from FPL API.")

        # Upsert (update or insert) the data into the Supabase table
        supabase.table("fpl_data").upsert(
            {"data_type": "bootstrap-static", "payload": bootstrap_data},
            on_conflict="data_type"
        ).execute()
        
        supabase.table("fpl_data").upsert(
            {"data_type": "fixtures", "payload": fixtures_data},
            on_conflict="data_type"
        ).execute()

        logging.info("✅ Successfully synced FPL data to Supabase.")

    except httpx.RequestError as e:
        logging.error(f"❌ Network error during FPL data fetch: {e}")
    except Exception as e:
        logging.error(f"❌ An error occurred during the Supabase sync process: {e}")

if __name__ == "__main__":
    asyncio.run(sync_fpl_data_to_supabase())
