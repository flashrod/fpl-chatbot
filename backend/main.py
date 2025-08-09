import os
import httpx
import asyncio
import pandas as pd
from pathlib import Path
from typing import List, Tuple
import re
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from fastapi.responses import StreamingResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import google.generativeai as genai

# Import your services
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
FPL_API_BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_API_FIXTURES = "https://fantasy.premierleague.com/api/fixtures/"
FPL_API_TEAM_PICKS = "https://fantasy.premierleague.com/api/entry/{team_id}/event/{gameweek}/picks/"
DATA_DIR = Path(__file__).parent / "fpl_data"
FBREF_STATS_PATH = DATA_DIR / "fbref_player_stats.csv"

# --- FIX: Add Headers to Mimic a Browser ---
API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# --- In-Memory Stores ---
master_fpl_data = None
current_gameweek_id = None
is_game_live = False
scheduler = AsyncIOScheduler()

# --- FastAPI App ---
app = FastAPI(title="FPL AI Chatbot API")

# --- Core Data Processing ---
async def load_and_process_all_data():
    global master_fpl_data, current_gameweek_id, is_game_live
    logging.info("🔄 Starting data update process...")
    try:
        # --- FIX: Use headers in the request ---
        async with httpx.AsyncClient(headers=API_HEADERS, timeout=30.0) as client:
            bootstrap_res, fixtures_res = await asyncio.gather(
                client.get(FPL_API_BOOTSTRAP),
                client.get(FPL_API_FIXTURES)
            )
        bootstrap_res.raise_for_status()
        fixtures_res.raise_for_status()
    except httpx.HTTPStatusError as e:
        logging.error(f"❌ HTTP error: {e.response.status_code} - {e.response.text}")
        return
    except httpx.RequestError as e:
        logging.error(f"❌ Network error during FPL data fetch: {e}")
        return

    bootstrap_data = bootstrap_res.json()
    fixtures_data = fixtures_res.json()

    is_game_live = any(gw.get('is_current', False) for gw in bootstrap_data['events'])
    current_gameweek_id = next((gw['id'] for gw in bootstrap_data['events'] if gw.get('is_current', False)), 1)

    teams_map = {team['id']: team['short_name'] for team in bootstrap_data['teams']}
    position_map = {p_type['id']: p_type['singular_name_short'] for p_type in bootstrap_data['element_types']}
    app.state.full_team_names = {team['short_name']: team['name'] for team in bootstrap_data['teams']}

    fpl_players_df = pd.DataFrame(bootstrap_data['elements']).rename(columns={'web_name': 'Player'})
    fpl_players_df['team_name'] = fpl_players_df['team'].map(teams_map)
    fpl_players_df['position'] = fpl_players_df['element_type'].map(position_map)

    if FBREF_STATS_PATH.exists():
        fbref_df = pd.read_csv(FBREF_STATS_PATH)
        fpl_players_df['Player_lower'] = fpl_players_df['Player'].str.lower()
        fbref_df['Player_lower'] = fbref_df['Player'].str.lower()
        merged_df = pd.merge(fpl_players_df, fbref_df, on='Player_lower', how='left', suffixes=('', '_fbref'))
    else:
        logging.error("❌ FBref stats file not found.")
        merged_df = fpl_players_df

    merged_df.drop_duplicates(subset=['id'], keep='first', inplace=True)
    merged_df.set_index('Player', inplace=True)
    master_fpl_data = merged_df
    logging.info("✅ Data update complete.")

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
    allow_origins=["*"], # Allow all for simplicity, can be restricted later
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
    return {"players": []} # Simplified for pre-season login

@app.get("/api/live-gameweek-data/{team_id}/{gameweek}")
async def get_live_gameweek_data(team_id: int, gameweek: int):
    raise HTTPException(status_code=404, detail="Live gameweek data feature is not yet available.")

# --- Context Builder ---
def build_context_for_question(question: str, all_players_df: pd.DataFrame, full_team_names: dict) -> str:
    question_lower = question.lower()
    
    trigger_words = ['top', 'most', 'best', 'cheapest', 'worst', 'easiest', 'hardest', 'fixture']
    if any(word in question_lower for word in trigger_words):
        if "cheapest" in question_lower and "defenders" in question_lower:
            defenders = all_players_df[all_players_df['position'] == 'DEF']
            cheapest = defenders.sort_values(by='now_cost', ascending=True).head(5)
            summary = "Here are the top 5 cheapest defenders:\n"
            for index, player in cheapest.iterrows():
                summary += f"- {player.name} ({player.team_name}) - £{player.now_cost/10.0:.1f}m\n"
            return summary

    player_names_found = []
    cleaned_question = re.sub(r'[^a-z0-9\s]', '', question_lower)
    if 'simple_name' not in all_players_df.columns:
        all_players_df['simple_name'] = all_players_df.index.str.lower().str.replace(r'[^a-z0-9\s]', '', regex=True)

    for name, player_data in all_players_df.iterrows():
        name_parts = player_data['simple_name'].split()
        if any(part in cleaned_question for part in name_parts if len(part) > 2):
            player_names_found.append(name)
    
    if player_names_found:
        context = ""
        for name in sorted(list(set(player_names_found))):
             if name in master_fpl_data.index:
                context += master_fpl_data.loc[name].to_json() + "\n"
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
        context_block = build_context_for_question(request.question, master_fpl_data, app.state.full_team_names)
        
        async for chunk in gemini_service.get_ai_response_stream(
            request.question, gemini_history, context_block, is_game_live
        ):
             yield chunk

    except Exception as e:
        logging.error(f"Error during chat streaming: {e}")
        yield "Sorry, I encountered a critical server error.\n\n"
