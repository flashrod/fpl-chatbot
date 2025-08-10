import os
import asyncio
import pandas as pd
from pathlib import Path
from typing import List, Optional
import re
import logging
from fastapi import FastAPI, HTTPException, Request
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
is_game_live: bool = False
scheduler = AsyncIOScheduler()

# --- FastAPI App ---
app = FastAPI(title="FPL AI Chatbot API")

# --- Core Data Processing ---
async def load_and_process_all_data():
    """
    Loads bootstrap static + fixtures from Supabase, processes them, merges with FBref,
    and builds the master_fpl_data DataFrame.
    """
    global master_fpl_data, current_gameweek_id, is_game_live

    logging.info("🔄 Starting data update process from Supabase...")
    
    try:
        bootstrap_response = supabase.table("fpl_data").select("payload").eq("data_type", "bootstrap-static").single().execute()
        fixtures_response = supabase.table("fpl_data").select("payload").eq("data_type", "fixtures").single().execute()

        if not bootstrap_response.data or not fixtures_response.data:
            raise ValueError("Required data not found in Supabase. Run the sync script first.")

        bootstrap_data = bootstrap_response.data['payload']
        fixtures_data = fixtures_response.data['payload']
        
    except Exception as e:
        logging.error(f"❌ Failed to fetch data from Supabase: {e}")
        return

    is_game_live = any(gw.get('is_current', False) for gw in bootstrap_data.get('events', []))
    current_gameweek_id = next((gw['id'] for gw in bootstrap_data.get('events', []) if gw.get('is_current', False)), 1)

    teams_map = {team['id']: team['short_name'] for team in bootstrap_data.get('teams', [])}
    app.state.full_team_names = {team['short_name']: team['name'] for team in bootstrap_data.get('teams', [])}
    position_map = {p_type['id']: p_type['singular_name_short'] for p_type in bootstrap_data.get('element_types', [])}
    
    # --- Process Raw Fixture Data ---
    team_fixtures = {team_id: [] for team_id in teams_map.keys()}
    for fixture in fixtures_data:
        if fixture.get('event') and fixture['event'] >= current_gameweek_id:
            team_fixtures[fixture['team_h']].append({
                'gameweek': fixture['event'],
                'opponent': teams_map.get(fixture['team_a'], 'N/A'),
                'difficulty': fixture['team_h_difficulty']
            })
            team_fixtures[fixture['team_a']].append({
                'gameweek': fixture['event'],
                'opponent': teams_map.get(fixture['team_h'], 'N/A'),
                'difficulty': fixture['team_a_difficulty']
            })

    team_difficulty_details = {}
    for team_id, fixtures in team_fixtures.items():
        sorted_fixtures = sorted(fixtures, key=lambda x: x['gameweek'])
        next_5 = sorted_fixtures[:5]
        avg_difficulty = sum(f['difficulty'] for f in next_5) / len(next_5) if next_5 else 0
        team_difficulty_details[team_id] = {
            'fixture_details': sorted_fixtures,
            'avg_fixture_difficulty': avg_difficulty
        }

    # --- Build Main DataFrame ---
    fpl_players_df = pd.DataFrame(bootstrap_data.get('elements', [])).rename(columns={'web_name': 'Player'})
    fpl_players_df['team_name'] = fpl_players_df['team'].map(teams_map)
    fpl_players_df['position'] = fpl_players_df['element_type'].map(position_map)
    fpl_players_df['simple_name'] = fpl_players_df['Player'].str.lower().str.replace(r'[^a-z0-9\s]', '', regex=True).str.strip()
    fpl_players_df['form'] = pd.to_numeric(fpl_players_df['form'], errors='coerce').fillna(0)
    
    # Add the newly processed fixture data to the DataFrame
    fpl_players_df['fixture_details'] = fpl_players_df['team'].map(lambda x: team_difficulty_details.get(x, {}).get('fixture_details', []))
    fpl_players_df['avg_fixture_difficulty'] = fpl_players_df['team'].map(lambda x: team_difficulty_details.get(x, {}).get('avg_fixture_difficulty', 0))

    # --- Merge with FBref (Optional) ---
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
    allow_origins=["https://fpl-chatbot.vercel.app", "http://localhost:5173"],
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
        "status": "ok",
        "is_game_live": is_game_live,
        "current_gameweek": current_gameweek_id,
        "players_in_master_df": len(master_fpl_data) if master_fpl_data is not None else 0
    }

@app.get("/api/fixture-difficulty")
async def get_fixture_difficulty_data():
    if master_fpl_data is None:
        raise HTTPException(status_code=503, detail="Data is not yet available.")
    try:
        return chip_service.get_all_team_fixture_difficulty(master_fpl_data)
    except Exception as e:
        logging.error(f"❌ Error in get_fixture_difficulty_data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to calculate fixture difficulty.")

@app.get("/api/chip-recommendations")
async def get_chip_recommendations_data():
    if master_fpl_data is None:
        raise HTTPException(status_code=503, detail="Data is not yet available.")
    return chip_service.calculate_chip_recommendations(master_fpl_data)

@app.get("/api/get-team-data/{team_id}")
async def get_team_data(team_id: int):
    if master_fpl_data is None:
        raise HTTPException(status_code=503, detail="Server is still initializing.")
    return {"players": []}

@app.get("/api/live-gameweek-data/{team_id}/{gameweek}")
async def get_live_gameweek_data(team_id: int, gameweek: int):
    raise HTTPException(status_code=404, detail="Live gameweek data feature is not yet available.")

# --- Context Builder ---
def build_context_for_question(question: str, all_players_df: pd.DataFrame) -> str:
    """
    Analyzes the user's question to build a relevant context string of data
    for the AI to use when generating a response.
    """
    if all_players_df is None or 'simple_name' not in all_players_df.columns:
        return ""

    question_lower = question.lower()
    context = ""

    # --- Keyword-based Context Building ---

    # 1. Handle questions about price/cost
    if any(word in question_lower for word in ["expensive", "cheapest", "cost", "price"]):
        # Determine sorting order
        ascending = "cheapest" in question_lower
        
        # Filter by position if mentioned
        pos_df = all_players_df
        if "defender" in question_lower:
            pos_df = all_players_df[all_players_df['position'] == 'DEF']
        elif "midfielder" in question_lower:
            pos_df = all_players_df[all_players_df['position'] == 'MID']
        elif "forward" in question_lower:
            pos_df = all_players_df[all_players_df['position'] == 'FWD']

        sorted_players = pos_df.sort_values(by='now_cost', ascending=ascending).head(5)
        
        context += "Top 5 Players by Price:\n"
        for name, player in sorted_players.iterrows():
            context += f"- {name} ({player.get('team_name', '')}): £{player.get('now_cost', 0) / 10.0:.1f}m\n"
        return context

    # 2. Handle questions about top players/form/points
    if any(word in question_lower for word in ["top", "best", "form", "points"]):
        sorted_players = all_players_df.sort_values(by='total_points', ascending=False).head(5)
        context += "Top 5 Players by Total Points:\n"
        for name, player in sorted_players.iterrows():
            context += f"- {name} ({player.get('team_name', '')}): {player.get('total_points', 0)} points\n"
        return context
        
    # --- Player Name Matching (Fallback) ---
    
    cleaned_question = re.sub(r'[^a-z0-9\s]', '', question_lower)
    player_names_found = []
    simple_map = {row['simple_name']: idx for idx, row in all_players_df.iterrows()}

    for sname, canonical_name in simple_map.items():
        if re.search(r'\b' + re.escape(sname) + r'\b', cleaned_question):
            player_names_found.append(canonical_name)

    if player_names_found:
        unique_players = sorted(list(set(player_names_found)))
        logging.info(f"👨‍💻 Found players in question: {unique_players}")
        context += "Player Data:\n"
        for name in unique_players:
            if name in all_players_df.index:
                try:
                    player_data = all_players_df.loc[name][[
                        'team_name', 'position', 'now_cost', 'total_points', 
                        'goals_scored', 'assists', 'status', 'news'
                    ]].to_dict()
                    context_str = ", ".join(f"{key}: {value}" for key, value in player_data.items() if value and pd.notna(value))
                    context += f"- {name}: {context_str}\n"
                except Exception as e:
                    logging.warning(f"Could not build context for player {name}: {e}")
        return context

    # If no specific context is built, return empty
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
        # ✅ FINAL FIX: Validate and map roles before sending to the AI
        for message in request.history:
            # Safely get the role and text from the message
            role = message.get("role", "").lower()
            text = message.get("text")

            # The Gemini API uses 'model' for its responses.
            # If the frontend uses 'assistant', we map it to 'model'.
            if role == "assistant":
                role = "model"
            
            # Only add messages to the history if they have a valid role AND text
            if role in ["user", "model"] and text:
                gemini_history.append({
                    "role": role,
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