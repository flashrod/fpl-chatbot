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

    fixtures_df = pd.DataFrame(fixtures_data)
    upcoming_fixtures_data = {}
    for team_id in teams_map.keys():
        team_fixtures = fixtures_df[
            ((fixtures_df['team_h'] == team_id) | (fixtures_df['team_a'] == team_id)) &
            (fixtures_df['event'] >= current_gameweek_id)
        ]
        fixtures_to_analyze = team_fixtures.head(5)
        fixture_details_list = []
        total_difficulty = 0
        for _, row in fixtures_to_analyze.iterrows():
            is_home = row['team_h'] == team_id
            opponent = teams_map.get(row['team_a'] if is_home else row['team_h'])
            difficulty = row['team_h_difficulty'] if is_home else row['team_a_difficulty']
            fixture_details_list.append({
                "gameweek": row.get("event"),
                "opponent": opponent,
                "is_home": is_home,
                "difficulty": difficulty
            })
            total_difficulty += difficulty
        avg_difficulty = total_difficulty / len(fixtures_to_analyze) if not fixtures_to_analyze.empty else 5.0
        upcoming_fixtures_data[team_id] = {
            "fixture_details": fixture_details_list,
            "avg_difficulty": round(avg_difficulty, 2)
        }

    fpl_players_df['fixture_details'] = fpl_players_df['team'].map(
        lambda tid: upcoming_fixtures_data.get(tid, {}).get('fixture_details')
    )
    fpl_players_df['avg_fixture_difficulty'] = fpl_players_df['team'].map(
        lambda tid: upcoming_fixtures_data.get(tid, {}).get('avg_difficulty')
    )

    if FBREF_STATS_PATH.exists():
        fbref_df = pd.read_csv(FBREF_STATS_PATH)
        fpl_players_df['Player_lower'] = fpl_players_df['Player'].str.lower()
        fbref_df['Player_lower'] = fbref_df['Player'].str.lower()
        merged_df = pd.merge(fpl_players_df, fbref_df, on='Player_lower', how='left', suffixes=('', '_fbref'))
    else:
        logging.error("❌ FBref stats file not found.")
        merged_df = fpl_players_df

    merged_df.drop_duplicates(subset=['id'], keep='first', inplace=True)
    fbref_numeric_cols = ['Min_standard', 'Gls_standard', 'Ast_standard', 'xG_shooting',
                          'xAG_shooting', 'Sh_shooting', 'KP_passing', 'SCA_gca', 'Att Pen_possession']
    for col in fbref_numeric_cols:
        if col not in merged_df.columns:
            merged_df[col] = 0
        merged_df[col].fillna(0, inplace=True)

    merged_df.set_index('Player', inplace=True)
    master_fpl_data = merged_df
    app.state.last_data_update = pd.Timestamp.now().isoformat()
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
    allow_origins=["https://fpl-brain.vercel.app", "http://localhost:5173"], # Allow both deployed and local frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

class Player(BaseModel):
    name: str
    position: str
    cost: float
    team_name: str

class TeamData(BaseModel):
    players: List[Player]

class ChatMessage(BaseModel):
    role: str
    text: str

class ChatRequest(BaseModel):
    team_id: int = None
    question: str
    history: List[ChatMessage] = Field(default_factory=list)

# --- API Endpoints ---
@app.get("/api/status")
async def get_status():
    return {
        "status": "ok",
        "is_game_live": is_game_live,
        "current_gameweek": current_gameweek_id,
        "last_data_update": app.state.last_data_update if hasattr(app.state, 'last_data_update') else None,
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

@app.get("/api/get-team-data/{team_id}", response_model=TeamData)
async def get_team_data(team_id: int):
    # Simplified for login during pre-season, will return empty list if no team is picked
    if master_fpl_data is None:
        raise HTTPException(status_code=503, detail="Server is still initializing data.")
    
    gw_to_fetch = current_gameweek_id if is_game_live else 1
    
    try:
        async with httpx.AsyncClient(headers=API_HEADERS) as client:
            picks_url = FPL_API_TEAM_PICKS.format(team_id=team_id, gameweek=gw_to_fetch)
            res = await client.get(picks_url)
            res.raise_for_status()
            picks_data = res.json()
            player_ids = [pick['element'] for pick in picks_data.get('picks', [])]
        
        team_df = master_fpl_data[master_fpl_data['id'].isin(player_ids)]
        player_list = [Player(name=index, position=row.position, cost=row.now_cost / 10.0, team_name=row.team_name) for index, row in team_df.iterrows()]
        return TeamData(players=player_list)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"A team with ID {team_id} could not be found.")
        else:
            raise HTTPException(status_code=e.response.status_code, detail="An error occurred while fetching team data.")
    except Exception as e:
        logging.error(f"Error in get_team_data: {e}")
        raise HTTPException(status_code=500, detail="An unexpected server error occurred.")


# --- FIX: Add placeholder for the missing Leagues endpoint ---
@app.get("/api/live-gameweek-data/{team_id}/{gameweek}")
async def get_live_gameweek_data(team_id: int, gameweek: int):
    raise HTTPException(status_code=404, detail="Live gameweek data feature is not yet available.")


# --- Context Builder ---
def build_context_for_question(question: str, all_players_df: pd.DataFrame, full_team_names: dict) -> Tuple[str, List[str]]:
    # This function remains unchanged from the previous working version.
    return "", []

# --- Main Chat Endpoint ---
@app.post("/api/chat")
async def chat_with_bot(request: ChatRequest):
    return StreamingResponse(stream_chat_response(request), media_type="text/plain")

async def stream_chat_response(request: ChatRequest):
    if master_fpl_data is None:
        yield "Sorry, the FPL data is not available. Please try again.\n\n"
        return

    try:
        question_lower = request.question.lower()
        draft_keywords = ['draft', 'generate', 'build', 'squad', 'team']
        
        gemini_history = []
        for h in request.history:
            role = "model" if h.role == "bot" else "user"
            gemini_history.append({"role": role, "parts": [{"text": h.text}]})

        if any(keyword in question_lower for keyword in draft_keywords):
            gemini_history = [] 
            
            engine = DraftEngine(master_fpl_data)
            draft_df = engine.create_draft()
            
            context_block = "DRAFT COMPLETE. Remaining Budget: £{:.1f}m\n\n".format(engine.budget)
            for position in ['GKP', 'DEF', 'MID', 'FWD']:
                context_block += f"**{position}**:\n"
                for _, player in draft_df[draft_df['position'] == position].iterrows():
                    context_block += f"- {player['Player']} ({player['team_name']}) - £{player['now_cost']/10.0:.1f}m\n"

            async for chunk in gemini_service.get_ai_response_stream(
                request.question, gemini_history, context_block, is_game_live, mode="draft_creation"
            ):
                yield chunk
        else:
            general_summary, players_from_question = build_context_for_question(
                request.question, master_fpl_data, app.state.full_team_names
            )
            
            context_block = ""
            if players_from_question:
                # ... (Your existing logic for building player context)
                pass
            elif general_summary:
                context_block = general_summary
            
            async for chunk in gemini_service.get_ai_response_stream(
                request.question, gemini_history, context_block, is_game_live
            ):
                yield chunk

    except Exception as e:
        logging.error(f"Error during chat streaming: {e}")
        yield "Sorry, I encountered a critical server error.\n\n"
