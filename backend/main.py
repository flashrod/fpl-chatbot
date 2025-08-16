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
    position_map = {p_type['id']: p_type['singular_name_short'] for p_type in bootstrap_data.get('element_types', [])}
    
    team_fixtures = {team['id']: [] for team in bootstrap_data.get('teams', [])}
    for fixture in fixtures_data:
        if fixture.get('event') and fixture['event'] >= current_gameweek_id:
            team_fixtures[fixture['team_h']].append({'gameweek': fixture['event'], 'opponent': teams_map.get(fixture['team_a'], 'N/A'), 'difficulty': fixture['team_h_difficulty'], 'is_home': True})
            team_fixtures[fixture['team_a']].append({'gameweek': fixture['event'], 'opponent': teams_map.get(fixture['team_h'], 'N/A'), 'difficulty': fixture['team_a_difficulty'], 'is_home': False})

    fpl_players_df = pd.DataFrame(bootstrap_data.get('elements', [])).rename(columns={'web_name': 'Player'})
    fpl_players_df['team_name'] = fpl_players_df['team'].map(teams_map)
    fpl_players_df['position'] = fpl_players_df['element_type'].map(position_map)
    fpl_players_df['simple_name'] = fpl_players_df['Player'].str.lower().str.replace(r'[^a-z0-9\s]', '', regex=True).str.strip()
    fpl_players_df['form'] = pd.to_numeric(fpl_players_df['form'], errors='coerce').fillna(0)
    fpl_players_df['points_per_game'] = pd.to_numeric(fpl_players_df['points_per_game'], errors='coerce').fillna(0)
    
    # Attach the full list of upcoming fixtures to each player
    fpl_players_df['fixture_details'] = fpl_players_df['team'].map(lambda x: sorted(team_fixtures.get(x, []), key=lambda f: f['gameweek']))

    merged_df = fpl_players_df
    merged_df.drop_duplicates(subset=['id'], keep='first', inplace=True)
    merged_df.set_index('Player', inplace=True)
    master_fpl_data = merged_df
    logging.info("✅ Data update complete. players=%s, gameweek=%s, is_live=%s", len(master_fpl_data), current_gameweek_id, is_game_live)

# --- App Lifecycle & Schemas ---
@app.on_event("startup")
async def startup_event():
    await load_and_process_all_data()
    scheduler.add_job(load_and_process_all_data, IntervalTrigger(minutes=15))
    scheduler.start()

@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown()

app.add_middleware(CORSMiddleware,
    allow_origins=["https://fpl-chatbot.vercel.app", "https://fpl-brain.vercel.app", "http://localhost:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)

class ChatRequest(BaseModel):
    question: str
    history: List[dict] = Field(default_factory=list)

# --- API Endpoints ---
@app.get("/api/status")
async def get_status():
    if master_fpl_data is None: return {"status": "initializing"}
    return {"status": "ok", "current_gameweek": current_gameweek_id}

@app.get("/api/fixture-difficulty")
async def get_fixture_difficulty_data():
    if master_fpl_data is None: raise HTTPException(status_code=503, detail="Data not available.")
    return chip_service.get_adjusted_fixture_difficulty(master_fpl_data, teams_data_store, current_gameweek_id)

@app.get("/api/chip-recommendations")
async def get_chip_recommendations_data():
    if master_fpl_data is None: raise HTTPException(status_code=503, detail="Data not available.")
    return chip_service.calculate_chip_recommendations_new(master_fpl_data, current_gameweek_id)

# --- CONTEXT BUILDER ---
def build_context_for_question(question: str, all_players_df: pd.DataFrame) -> str:
    if all_players_df is None: return ""
    question_lower = question.lower()
    
    # Intent 1: Transfer Search
    transfer_triggers = ['buy', 'get', 'transfer', 'replace', 'midfielder', 'forward', 'defender']
    budget_match = re.search(r'(\d{1,2}(\.\d{1,2})?)m', question_lower)
    if any(trigger in question_lower for trigger in transfer_triggers) and budget_match:
        budget = float(budget_match.group(1)) * 10
        position = ""
        if 'midfielder' in question_lower: position = 'MID'
        elif 'forward' in question_lower: position = 'FWD'
        elif 'defender' in question_lower: position = 'DEF'
        df_filtered = all_players_df.copy()
        if position: df_filtered = df_filtered[df_filtered['position'] == position]
        df_filtered = df_filtered[df_filtered['now_cost'] <= budget]
        df_filtered['score'] = (pd.to_numeric(df_filtered['form']) * 1.5 + pd.to_numeric(df_filtered.get('ict_index', 0)) * 1.0 + pd.to_numeric(df_filtered['points_per_game']) * 1.2)
        top_candidates = df_filtered.sort_values(by='score', ascending=False).head(5)
        if not top_candidates.empty:
            context = f"Top transfer candidates (Position: {position or 'Any'}, Budget: £{budget/10.0:.1f}m):\n"
            for name, player in top_candidates.iterrows():
                fixtures = ", ".join([f"{f['opponent']}({'H' if f['is_home'] else 'A'})" for f in player.get('fixture_details', [])[:5]])
                context += f"- {name} ({player.get('team_name')}, £{player.get('now_cost',0)/10.0:.1f}m): Form: {player.get('form',0)}, Fixtures: {fixtures}\n"
            return context

    # Intent 2: Best Value Search
    value_triggers = ['value', 'undervalued', 'points per million']
    if any(trigger in question_lower for trigger in value_triggers):
        df_value = all_players_df.copy()
        df_value = df_value[pd.to_numeric(df_value['total_points']) > 50]
        if not df_value.empty:
            df_value['points_per_million'] = pd.to_numeric(df_value['total_points']) / (pd.to_numeric(df_value['now_cost']) / 10.0)
            top_value_players = df_value.sort_values(by='points_per_million', ascending=False).head(10)
            context = "Top 10 best value players (>50 total points):\n"
            for name, player in top_value_players.iterrows():
                context += f"- {name} ({player.get('team_name')}, £{player.get('now_cost',0)/10.0:.1f}m): {player.get('points_per_million', 0):.2f} PPM\n"
            return context

    # Intent 3: Specific Player Lookup
    player_names_found = []
    cleaned_question = re.sub(r"['’]s\b", "", question_lower)
    df_for_lookup = all_players_df.reset_index()
    for _, row in df_for_lookup.iterrows():
        if row['simple_name'] in cleaned_question:
            player_names_found.append(row['Player'])
    if player_names_found:
        unique_players = sorted(list(set(player_names_found)))
        context = "Player Data:\n"
        for name in unique_players:
            if name in all_players_df.index:
                player_data = all_players_df.loc[name]
                fixtures = ", ".join([f"{f['opponent']}({'H' if f['is_home'] else 'A'})" for f in player_data.get('fixture_details', [])[:5]])
                context += f"- {name} ({player_data.get('team_name')}, £{player_data.get('now_cost',0)/10.0:.1f}m): Points: {player_data.get('total_points',0)}, Form: {player_data.get('form',0)}, Fixtures: {fixtures}\n"
        return context
    return ""

# --- Main Chat Endpoint ---
@app.post("/api/chat")
async def chat_with_bot(request: ChatRequest):
    return StreamingResponse(stream_chat_response(request), media_type="text/plain")

async def stream_chat_response(request: ChatRequest):
    if master_fpl_data is None:
        yield "Sorry, data is initializing. Please try again in a moment.\n"
        return
    try:
        context_block = build_context_for_question(request.question, master_fpl_data)
        gemini_history = []
        for message in request.history:
            gemini_history.append({"role": "model" if message.get("role") != "user" else "user", "parts": [{"text": message.get("text")}]})
        
        async for chunk in gemini_service.get_ai_response_stream(request.question, gemini_history, context_block, is_game_live):
            yield chunk
            
    except Exception as e:
        logging.error(f"Error during chat streaming: {e}", exc_info=True)
        yield "A server error occurred.\n"