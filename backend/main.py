# main.py
import os
import httpx
import asyncio
import pandas as pd
from pathlib import Path
from typing import List, Optional
import re
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from fastapi.responses import StreamingResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import time
import google.generativeai as genai

# Import your services (placeholders in user's code)
import chip_service
import gemini_service
from draft_service import DraftEngine

# --- Configuration & Logging ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env file.")
genai.configure(api_key=GEMINI_API_KEY)

# --- Paths & URLs ---
FPL_HOME_URL = "https://fantasy.premierleague.com/"
FPL_API_BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_API_FIXTURES = "https://fantasy.premierleague.com/api/fixtures/"
FPL_API_TEAM_PICKS = "https://fantasy.premierleague.com/api/entry/{team_id}/event/{gameweek}/picks/"
DATA_DIR = Path(__file__).parent / "fpl_data"
BOOTSTRAP_CACHE = DATA_DIR / "bootstrap-static.json"
FIXTURES_CACHE = DATA_DIR / "fixtures.json"
FBREF_STATS_PATH = DATA_DIR / "fbref_player_stats.csv"

# Optional proxy env var: "http://user:pass@host:port" or "http://host:port"
FPL_PROXY_URL = os.getenv("FPL_PROXY_URL", None)

# --- HTTP headers: more complete browser-like headers ---
API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://fantasy.premierleague.com/",
    "Origin": "https://fantasy.premierleague.com",
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Connection": "keep-alive",
}

# --- In-Memory Stores ---
master_fpl_data: Optional[pd.DataFrame] = None
current_gameweek_id: Optional[int] = None
is_game_live: bool = False
scheduler = AsyncIOScheduler()

# persistent in-memory cookies (survive across scheduler refreshes within the process)
fpl_cookies: Optional[httpx.Cookies] = None

# --- FastAPI App ---
app = FastAPI(title="FPL AI Chatbot API")

# --- Helper functions ---
def save_json_to_cache(path: Path, data: dict):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        import json
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except Exception as e:
        logging.warning(f"Could not write cache {path}: {e}")

def read_json_cache(path: Path):
    if not path.exists():
        return None
    try:
        import json
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:
        logging.warning(f"Could not read cache {path}: {e}")
        return None

async def fetch_with_retries(url: str, client: httpx.AsyncClient, cookies: Optional[httpx.Cookies] = None, max_retries: int = 3, initial_wait: float = 1.0):
    """
    Fetch URL with exponential backoff. Pass cookies (if any) to the request.
    Returns httpx.Response on success or raises after retries.
    """
    attempt = 0
    wait = initial_wait
    while attempt < max_retries:
        attempt += 1
        try:
            logging.info(f"HTTP Request (attempt {attempt}): GET {url}")
            resp = await client.get(url, timeout=30.0, headers=API_HEADERS, cookies=cookies)
            if resp.status_code == 403:
                # Log a short preview of the body for debugging
                body_preview = (resp.text or "")[:500].replace("\n", " ")
                logging.warning(f"Received 403 from {url}. Response preview: {body_preview}")
                # Raise HTTPStatusError so caller can decide to refresh cookies
                raise httpx.HTTPStatusError("403 Forbidden", request=resp.request, response=resp)
            resp.raise_for_status()
            return resp
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logging.warning(f"Request failed for {url} on attempt {attempt}: {e}")
            if attempt >= max_retries:
                logging.error(f"Max retries reached for {url}. Giving up.")
                raise
            await asyncio.sleep(wait)
            wait *= 2.0

# --- Core Data Processing ---
async def load_and_process_all_data():
    """
    Loads bootstrap static + fixtures from FPL API, merges with FBref if available,
    and builds the master_fpl_data DataFrame. Includes cookie handling and caching fallback.
    """
    global master_fpl_data, current_gameweek_id, is_game_live, fpl_cookies

    logging.info("🔄 Starting data update process...")
    DATA_DIR.mkdir(exist_ok=True)

    # client config; try http2 but we'll gracefully degrade if environment lacks h2
    base_client_args = {
        "timeout": 30.0,
        "follow_redirects": True
    }
    if FPL_PROXY_URL:
        base_client_args["proxies"] = {"all": FPL_PROXY_URL}

    # We'll attempt to create an AsyncClient with http2=True first, otherwise fallback to HTTP/1.1
    client = None
    try:
        client = httpx.AsyncClient(http2=True, headers=API_HEADERS, **base_client_args)
        logging.info("Initialized httpx AsyncClient with http2=True")
    except Exception as e:
        logging.warning(f"Could not initialize http2 client (h2 might be missing): {e}. Falling back to HTTP/1.1 client.")
        client = httpx.AsyncClient(http2=False, headers=API_HEADERS, **base_client_args)

    try:
        async with client:
            # Step 1 — Acquire cookies from homepage if we don't already have them
            if not fpl_cookies:
                try:
                    logging.info("Fetching cookies from FPL homepage...")
                    home_resp = await client.get(FPL_HOME_URL, timeout=30.0, headers=API_HEADERS)
                    home_resp.raise_for_status()
                    fpl_cookies = home_resp.cookies
                    logging.info(f"Acquired {len(fpl_cookies)} cookies from homepage.")
                except Exception as e:
                    logging.warning(f"Failed to fetch homepage cookies: {e}. Proceeding without cookies and will try cached data on failure.")

            # Step 2 — Fetch API endpoints with cookies (if any)
            try:
                tasks = [
                    fetch_with_retries(FPL_API_BOOTSTRAP, client, cookies=fpl_cookies),
                    fetch_with_retries(FPL_API_FIXTURES, client, cookies=fpl_cookies)
                ]
                bootstrap_res, fixtures_res = await asyncio.gather(*tasks)
            except httpx.HTTPStatusError as e:
                # If we hit 403, try refreshing cookies once and retry
                if e.response is not None and e.response.status_code == 403:
                    logging.warning("403 detected while fetching API data — attempting to refresh cookies and retry once.")
                    try:
                        home_resp = await client.get(FPL_HOME_URL, timeout=30.0, headers=API_HEADERS)
                        home_resp.raise_for_status()
                        fpl_cookies = home_resp.cookies
                        logging.info("Refreshed cookies; retrying API requests...")
                        tasks = [
                            fetch_with_retries(FPL_API_BOOTSTRAP, client, cookies=fpl_cookies),
                            fetch_with_retries(FPL_API_FIXTURES, client, cookies=fpl_cookies)
                        ]
                        bootstrap_res, fixtures_res = await asyncio.gather(*tasks)
                    except Exception as e2:
                        logging.error(f"Retry after cookie refresh failed: {e2}")
                        raise
                else:
                    raise

        # If we get here, we have successful responses
        bootstrap_data = bootstrap_res.json()
        fixtures_data = fixtures_res.json()

        # Save to local cache for fallback
        save_json_to_cache(BOOTSTRAP_CACHE, bootstrap_data)
        save_json_to_cache(FIXTURES_CACHE, fixtures_data)

    except Exception as e:
        logging.error(f"❌ Error fetching FPL API: {e}")
        # Try fallback to cached JSON files if they exist
        logging.info("Attempting to load cached data from fpl_data/ ...")
        bootstrap_data = read_json_cache(BOOTSTRAP_CACHE)
        fixtures_data = read_json_cache(FIXTURES_CACHE)
        if bootstrap_data is None or fixtures_data is None:
            logging.error("❌ No cached data available. Aborting load_and_process_all_data.")
            return
        logging.info("✅ Loaded cached bootstrap/fixtures from disk.")

    # --- Process data ---
    try:
        is_game_live = any(gw.get('is_current', False) for gw in bootstrap_data.get('events', []))
        current_gameweek_id = next((gw['id'] for gw in bootstrap_data.get('events', []) if gw.get('is_current', False)), 1)

        teams_map = {team['id']: team['short_name'] for team in bootstrap_data.get('teams', [])}
        position_map = {p_type['id']: p_type['singular_name_short'] for p_type in bootstrap_data.get('element_types', [])}
        # set mapping for full names on application state
        app.state.full_team_names = {team['short_name']: team['name'] for team in bootstrap_data.get('teams', [])}

        # Build DataFrame
        fpl_players_df = pd.DataFrame(bootstrap_data.get('elements', [])).rename(columns={'web_name': 'Player'})
        # map team & position
        fpl_players_df['team_name'] = fpl_players_df['team'].map(teams_map)
        fpl_players_df['position'] = fpl_players_df['element_type'].map(position_map)

        # lower-cased simple name once
        fpl_players_df['simple_name'] = fpl_players_df['Player'].str.lower().str.replace(r'[^a-z0-9\s]', '', regex=True)

        # Merge with FBref if available
        if FBREF_STATS_PATH.exists():
            try:
                fbref_df = pd.read_csv(FBREF_STATS_PATH)
                fbref_df['Player_lower'] = fbref_df['Player'].str.lower().str.replace(r'[^a-z0-9\s]', '', regex=True)
                fpl_players_df['Player_lower'] = fpl_players_df['Player'].str.lower().str.replace(r'[^a-z0-9\s]', '', regex=True)
                merged_df = pd.merge(fpl_players_df, fbref_df, left_on='Player_lower', right_on='Player_lower', how='left', suffixes=('', '_fbref'))
                # drop helper columns
                merged_df.drop(columns=['Player_lower'], inplace=True, errors='ignore')
            except Exception as e:
                logging.warning(f"Could not merge FBref data: {e}")
                merged_df = fpl_players_df
        else:
            logging.info("FBref stats file not found; proceeding without it.")
            merged_df = fpl_players_df

        # dedupe and index by Player name
        merged_df.drop_duplicates(subset=['id'], keep='first', inplace=True)
        merged_df.set_index('Player', inplace=True)

        master_fpl_data = merged_df
        logging.info("✅ Data update complete. players=%s, gameweek=%s, is_live=%s",
                     len(master_fpl_data), current_gameweek_id, is_game_live)

    except Exception as e:
        logging.error(f"❌ Error processing FPL data: {e}")
        return

# --- App Lifecycle & Schemas ---
@app.on_event("startup")
async def startup_event():
    DATA_DIR.mkdir(exist_ok=True)
    await load_and_process_all_data()
    scheduler.add_job(load_and_process_all_data, IntervalTrigger(hours=12))
    scheduler.start()
    logging.info("🚀 Server started.")

@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown()
    logging.info("👋 Scheduler shut down.")

app.add_middleware(CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

class ChatRequest(BaseModel):
    team_id: int = None
    question: str
    history: List[dict] = Field(default_factory=list)

# --- API Endpoints ---
@app.get("/api/status")
async def get_status():
    return {
        "status": "ok",
        "is_game_live": is_game_live,
        "current_gameweek": current_gameweek_id,
        "players_in_master_df": len(master_fpl_data) if master_fpl_data is not None else 0
    }

@app.get("/api/fixture-difficulty")
async def get_fixture_difficulty_data():
    if master_fpl_data is None:
        raise HTTPException(status_code=503, detail="Data is not yet available.")
    return chip_service.get_all_team_fixture_difficulty(master_fpl_data)

@app.get("/api/chip-recommendations")
async def get_chip_recommendations_data():
    if master_fpl_data is None:
        raise HTTPException(status_code=503, detail="Data is not yet available.")
    return chip_service.calculate_chip_recommendations(master_fpl_data)

@app.get("/api/get-team-data/{team_id}")
async def get_team_data(team_id: int):
    if master_fpl_data is None:
        raise HTTPException(status_code=503, detail="Server is still initializing.")
    return {"players": []}  # Simplified for pre-season login

@app.get("/api/live-gameweek-data/{team_id}/{gameweek}")
async def get_live_gameweek_data(team_id: int, gameweek: int):
    raise HTTPException(status_code=404, detail="Live gameweek data feature is not yet available.")

# --- Context Builder ---
def build_context_for_question(question: str, all_players_df: pd.DataFrame, full_team_names: dict) -> str:
    """
    Create a short context to pass to the AI based on the user's question.
    """
    if all_players_df is None:
        return ""

    question_lower = question.lower()

    trigger_words = ['top', 'most', 'best', 'cheapest', 'worst', 'easiest', 'hardest', 'fixture']
    if any(word in question_lower for word in trigger_words):
        if "cheapest" in question_lower and "defenders" in question_lower:
            defenders = all_players_df[all_players_df['position'] == 'DEF']
            cheapest = defenders.sort_values(by='now_cost', ascending=True).head(5)
            summary = "Here are the top 5 cheapest defenders:\n"
            for index, player in cheapest.iterrows():
                # player.name is index; index is a string
                summary += f"- {index} ({player.get('team_name','')}) - £{player.get('now_cost',0)/10.0:.1f}m\n"
            return summary

    # Name matching: look for players mentioned in the question
    player_names_found = []
    cleaned_question = re.sub(r'[^a-z0-9\s]', '', question_lower)

    # Ensure 'simple_name' column exists
    if 'simple_name' not in all_players_df.columns:
        # create a temporary simple_name if somehow missing
        all_players_df = all_players_df.copy()
        all_players_df['simple_name'] = all_players_df.index.str.lower().str.replace(r'[^a-z0-9\s]', '', regex=True)

    # Build a map from simple_name -> canonical index name to avoid repeated scanning
    simple_map = {}
    for idx, row in all_players_df.iterrows():
        simple_map[row['simple_name']] = idx

    # Check words in question against simple_name tokens
    q_words = set(cleaned_question.split())
    for sname, canonical in simple_map.items():
        s_parts = set(sname.split())
        # match if substantial overlap
        if len(s_parts & q_words) >= 1:
            player_names_found.append(canonical)

    if player_names_found:
        context = ""
        for name in sorted(list(set(player_names_found))):
            if name in master_fpl_data.index:
                try:
                    # Use to_dict for a compact representation
                    context += f"{name}: {master_fpl_data.loc[name].to_dict()}\n"
                except Exception:
                    # fallback: string
                    context += f"{name}\n"
        return context

    return ""

# --- Main Chat Endpoint ---
@app.post("/api/chat")
async def chat_with_bot(request: ChatRequest):
    return StreamingResponse(stream_chat_response(request), media_type="text/plain")

async def stream_chat_response(request: ChatRequest):
    if master_fpl_data is None:
        yield "Sorry, the FPL data is not available. Please try again.\n\n"
        return

    try:
        gemini_history = request.history
        context_block = build_context_for_question(request.question, master_fpl_data, getattr(app.state, "full_team_names", {}))

        async for chunk in gemini_service.get_ai_response_stream(
            request.question, gemini_history, context_block, is_game_live
        ):
            yield chunk

    except Exception as e:
        logging.error(f"Error during chat streaming: {e}", exc_info=True)
        yield "Sorry, I encountered a critical server error.\n\n"