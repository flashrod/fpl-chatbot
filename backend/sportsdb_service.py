# backend/sportsdb_service.py

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
SPORTSDB_API_KEY = os.getenv("SPORTSDB_API_KEY")
BASE_URL = f"https://www.thesportsdb.com/api/v1/json/{SPORTSDB_API_KEY}"

if not SPORTSDB_API_KEY or SPORTSDB_API_KEY == "YOUR_SPORTSDB_API_KEY":
    print("WARNING: SPORTSDB_API_KEY not found in .env file. Player details will be limited.")

async def get_all_epl_players() -> dict | None:
    """
    Fetches all players from the English Premier League from TheSportsDB.
    Returns a dictionary mapping player names to their details.
    """
    if not SPORTSDB_API_KEY:
        return None

    all_players_map = {}
    # TheSportsDB uses a URL-encoded league name
    league_name = "English%20Premier%20League"
    url = f"{BASE_URL}/search_all_players.php?l={league_name}"
    
    print("--- Starting bulk fetch of player data from TheSportsDB ---")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()

            if data and "player" in data:
                for player_details in data["player"]:
                    player_name = player_details.get("strPlayer")
                    if player_name:
                        all_players_map[player_name] = {
                            "nationality": player_details.get("strNationality"),
                            "status": player_details.get("strStatus"),
                            "description": player_details.get("strDescriptionEN"),
                        }
                print(f"✅ Successfully fetched details for {len(all_players_map)} players from TheSportsDB.")
                return all_players_map
            else:
                print("❌ No player data found in TheSportsDB response.")
                return None

        except httpx.RequestError as e:
            print(f"Network error during TheSportsDB bulk fetch: {e}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during TheSportsDB bulk fetch: {e}")
            return None
