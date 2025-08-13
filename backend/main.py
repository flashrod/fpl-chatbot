import os
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
import google.generativeai as genai
from supabase import create_client, Client

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

# --- Supabase Configuration ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Supabase URL and Key must be set in your .env file.")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Paths ---
DATA_DIR = Path(__file__).parent / "fpl_data"
FBREF_STATS_PATH = DATA_DIR / "fbref_player_stats.csv"

# --- In-Memory Stores ---
master_fpl_data: Optional[pd.DataFrame] = None
current_gameweek_id: Optional[int] = None
teams_data_store: Optional[list] = None
is_game_live: bool = False
scheduler = AsyncIOScheduler()

# --- FastAPI App ---
app = FastAPI(title="FPL AI Chatbot API")

# --- Core Data Processing ---
async def load_and_process_all_data():
    global master_fpl_data, current_gameweek_id, is_game_live, teams_data_store
    logging.info("🔄 Starting data update process from Supabase...")
    
    try:
        bootstrap_response = supabase.table("fpl_data").select("payload").eq("data_type", "bootstrap-static").single().execute()
        fixtures_response = supabase.table("fpl_data").select("payload").eq("data_type", "fixtures").single().execute()

        if not bootstrap_response.data or not fixtures_response.data:
            raise ValueError("Required data not found in Supabase. Run the sync script first.")

        bootstrap_data = bootstrap_response.data['payload']
        teams_data_store = bootstrap_data.get('teams', [])
        fixtures_data = fixtures_response.data['payload']
        
    except Exception as e:
        logging.error(f"❌ Failed to fetch data from Supabase: {e}")
        return

    is_game_live = any(gw.get('is_current', False) for gw in bootstrap_data.get('events', []))
    current_gameweek_id = next((gw['id'] for gw in bootstrap_data.get('events', []) if gw.get('is_current', False)), 1)

    teams_map = {team['id']: team['short_name'] for team in bootstrap_data.get('teams', [])}
    app.state.full_team_names = {team['short_name']: team['name'] for team in bootstrap_data.get('teams', [])}
    position_map = {p_type['id']: p_type['singular_name_short'] for p_type in bootstrap_data.get('element_types', [])}
    
    team_fixtures = {team_id: [] for team_id in teams_map.keys()}
    for fixture in fixtures_data:
        if fixture.get('event') and fixture['event'] >= current_gameweek_id:
            team_fixtures[fixture['team_h']].append({'gameweek': fixture['event'], 'opponent': teams_map.get(fixture['team_a'], 'N/A'), 'difficulty': fixture['team_h_difficulty'], 'is_home': True})
            team_fixtures[fixture['team_a']].append({'gameweek': fixture['event'], 'opponent': teams_map.get(fixture['team_h'], 'N/A'), 'difficulty': fixture['team_a_difficulty'], 'is_home': False})

    team_difficulty_details = {}
    for team_id, fixtures in team_fixtures.items():
        sorted_fixtures = sorted(fixtures, key=lambda x: x['gameweek'])
        next_5 = sorted_fixtures[:5]
        avg_difficulty = sum(f['difficulty'] for f in next_5) / len(next_5) if next_5 else 0
        team_difficulty_details[team_id] = {'fixture_details': next_5, 'avg_fixture_difficulty': avg_difficulty}

    fpl_players_df = pd.DataFrame(bootstrap_data.get('elements', [])).rename(columns={'web_name': 'Player'})
    fpl_players_df['team_name'] = fpl_players_df['team'].map(teams_map)
    fpl_players_df['position'] = fpl_players_df['element_type'].map(position_map)
    fpl_players_df['simple_name'] = fpl_players_df['Player'].str.lower().str.replace(r'[^a-z0-9\s]', '', regex=True).str.strip()
    fpl_players_df['form'] = pd.to_numeric(fpl_players_df['form'], errors='coerce').fillna(0)
    
    # This is a critical line for the new context builder. Make sure 'points_per_game' exists.
    if 'points_per_game' not in fpl_players_df.columns:
        fpl_players_df['points_per_game'] = pd.to_numeric(fpl_players_df['points_per_game'], errors='coerce').fillna(0)

    fpl_players_df['fixture_details'] = fpl_players_df['team'].map(lambda x: team_difficulty_details.get(x, {}).get('fixture_details', []))
    fpl_players_df['avg_fixture_difficulty'] = fpl_players_df['team'].map(lambda x: team_difficulty_details.get(x, {}).get('avg_fixture_difficulty', 0))

    if FBREF_STATS_PATH.exists():
        try:
            fbref_df = pd.read_csv(FBREF_STATS_PATH)
            fbref_df['Player_lower'] = fbref_df['Player'].str.lower().str.replace(r'[^a-z0-9\s]', '', regex=True).str.strip()
            merged_df = pd.merge(fpl_players_df, fbref_df, left_on='simple_name', right_on='Player_lower', how='left', suffixes=('', '_fbref'))
            merged_df.drop(columns=['Player_lower'], inplace=True, errors='ignore')
        except Exception as e:
            logging.warning(f"Could not merge FBref data: {e}")
            merged_df = fpl_players_df
    else:
        logging.info("FBref stats file not found; proceeding without it.")
        merged_df = fpl_players_df

    merged_df.drop_duplicates(subset=['id'], keep='first', inplace=True)
    merged_df.set_index('Player', inplace=True)

    master_fpl_data = merged_df
    logging.info("✅ Data update complete. players=%s, gameweek=%s, is_live=%s",
                 len(master_fpl_data), current_gameweek_id, is_game_live)

# --- App Lifecycle & Schemas ---
@app.on_event("startup")
async def startup_event():
    DATA_DIR.mkdir(exist_ok=True)
    await load_and_process_all_data()
    scheduler.add_job(load_and_process_all_data, IntervalTrigger(minutes=15))
    scheduler.start()
    logging.info("🚀 Server started.")

@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown()
    logging.info("👋 Scheduler shut down.")

app.add_middleware(CORSMiddleware,
    allow_origins=["https://fpl-chatbot.vercel.app", "https://fpl-brain.vercel.app", "http://localhost:5173"],
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
    if master_fpl_data is None:
        return {"status": "initializing", "players_in_master_df": 0}
    return {
        "status": "ok", "is_game_live": is_game_live,
        "current_gameweek": current_gameweek_id,
        "players_in_master_df": len(master_fpl_data) if master_fpl_data is not None else 0
    }

@app.get("/api/fixture-difficulty")
async def get_fixture_difficulty_data():
    if master_fpl_data is None or current_gameweek_id is None or teams_data_store is None:
        raise HTTPException(status_code=503, detail="Data is not yet available.")
    return chip_service.get_adjusted_fixture_difficulty(master_fpl_data, teams_data_store, current_gameweek_id)

@app.get("/api/chip-recommendations")
async def get_chip_recommendations_data():
    if master_fpl_data is None or current_gameweek_id is None:
        raise HTTPException(status_code=503, detail="Data is not yet available.")
    return chip_service.calculate_chip_recommendations_new(master_fpl_data, current_gameweek_id)

@app.get("/api/get-team-data/{team_id}")
async def get_team_data(team_id: int):
    if master_fpl_data is None: raise HTTPException(status_code=503, detail="Server is still initializing.")
    return {"players": []}

@app.get("/api/live-gameweek-data/{team_id}/{gameweek}")
async def get_live_gameweek_data(team_id: int, gameweek: int):
    raise HTTPException(status_code=404, detail="Live gameweek data feature is not yet available.")

# --- NEW, SMARTER CONTEXT BUILDER ---
# This entire function is replaced with the new version.
def build_context_for_question(question: str, all_players_df: pd.DataFrame) -> str:
    if all_players_df is None: return ""

    question_lower = question.lower()
    
    # --- Intent 1: Transfer Search ---
    transfer_triggers = ['buy', 'get', 'transfer in', 'replace', 'replacement for', 'midfielder', 'forward', 'defender', 'goalkeeper']
    budget_match = re.search(r'(under|over|less than|more than|for|at)?[ ]?(\d{1,2}(\.\d{1,2})?)m?', question_lower)
    
    if any(trigger in question_lower for trigger in transfer_triggers) and budget_match:
        budget = float(budget_match.group(2)) * 10 
        position = ""
        if 'midfielder' in question_lower: position = 'MID'
        elif 'forward' in question_lower: position = 'FWD'
        elif 'defender' in question_lower: position = 'DEF'
        elif 'goalkeeper' in question_lower: position = 'GKP'

        df_filtered = all_players_df.copy()
        if position:
            df_filtered = df_filtered[df_filtered['position'] == position]
        df_filtered = df_filtered[df_filtered['now_cost'] <= budget]

        df_filtered['score'] = (
            pd.to_numeric(df_filtered['form'], errors='coerce').fillna(0) * 1.5 +
            pd.to_numeric(df_filtered['ict_index'], errors='coerce').fillna(0) * 1.0 +
            pd.to_numeric(df_filtered['points_per_game'], errors='coerce').fillna(0) * 1.2
        )
        top_candidates = df_filtered.sort_values(by='score', ascending=False).head(5)

        if not top_candidates.empty:
            context = f"Here are the top {len(top_candidates)} transfer candidates matching the user's request (Position: {position or 'Any'}, Budget: £{budget/10.0:.1f}m):\n"
            for name, player in top_candidates.iterrows():
                fixtures = ", ".join([f"{f['opponent']}({'H' if f['is_home'] else 'A'})" for f in player.get('fixture_details', [])])
                context += f"- **{name}** ({player.get('team_name')}, {player.get('position')}, £{player.get('now_cost',0)/10.0:.1f}m): "
                context += f"Form: {player.get('form',0)}, ICT: {player.get('ict_index',0)}, Upcoming fixtures: {fixtures}\n"
            return context

    # --- Intent 2: Best Value Search ---
    value_triggers = ['value', 'undervalued', 'value for money', 'points per million']
    if any(trigger in question_lower for trigger in value_triggers):
        df_value = all_players_df.copy()
        df_value = df_value[pd.to_numeric(df_value['total_points'], errors='coerce').fillna(0) > 50]
        
        df_value['points_per_million'] = pd.to_numeric(df_value['total_points']) / (pd.to_numeric(df_value['now_cost']) / 10.0)
        
        top_value_players = df_value.sort_values(by='points_per_million', ascending=False).head(10)
        
        if not top_value_players.empty:
            context = "Here are the top 10 best value players based on Points Per Million (and have scored >50 total points):\n"
            for name, player in top_value_players.iterrows():
                context += (f"- **{name}** ({player.get('team_name')}, {player.get('position')}, £{player.get('now_cost',0)/10.0:.1f}m): "
                            f"**{player.get('points_per_million', 0):.2f} Points Per Million** (Total Points: {player.get('total_points',0)})\n")
            return context

    # --- Intent 3: Specific Player Lookup ---
    player_names_found = []
    cleaned_question = re.sub(r"['’]s\b", "", question_lower)

    for simple_name, full_name in all_players_df[['simple_name', 'Player']].itertuples(index=False):
        if simple_name in cleaned_question:
            player_names_found.append(full_name)
    
    if player_names_found:
        unique_players = sorted(list(set(player_names_found)))
        context = "Player Data:\n"
        for name in unique_players:
            if name in all_players_df.index:
                player_data = all_players_df.loc[name]
                fixtures = ", ".join([f"{f['opponent']}({'H' if f['is_home'] else 'A'})" for f in player_data.get('fixture_details', [])])
                context += f"- **{name}** ({player_data.get('team_name')}, {player.data.get('position')}, £{player_data.get('now_cost',0)/10.0:.1f}m): "
                context += f"Points: {player_data.get('total_points',0)}, Form: {player_data.get('form',0)}, ICT: {player_data.get('ict_index',0)}, Upcoming fixtures: {fixtures}\n"
        return context

    return ""

# --- Main Chat Endpoint ---
@app.post("/api/chat")
async def chat_with_bot(request: ChatRequest):
    return StreamingResponse(stream_chat_response(request), media_type="text/plain")

async def stream_chat_response(request: ChatRequest):
    if master_fpl_data is None:
        yield "Sorry, the FPL data is not available. The server might still be initializing. Please try again in a moment.\n"
        return

    try:
        gemini_history = []
        for message in request.history:
            role = message.get("role", "").lower()
            text = message.get("text")
            if role in ["user", "assistant", "bot"]:
                gemini_history.append({
                    "role": "model" if role != "user" else "user",
                    "parts": [{"text": text}]
                })

        context_block = build_context_for_question(request.question, master_fpl_data)
        
        async for chunk in gemini_service.get_ai_response_stream(
            request.question, gemini_history, context_block, is_game_live
        ):
            yield chunk
            
    except Exception as e:
        logging.error(f"Error during chat streaming: {e}", exc_info=True)
        yield "Sorry, I encountered a critical server error. The issue has been logged.\n"