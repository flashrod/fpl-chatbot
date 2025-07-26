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
        async with httpx.AsyncClient(timeout=30.0) as client:
            bootstrap_task = client.get(FPL_API_BOOTSTRAP)
            fixtures_task = client.get(FPL_API_FIXTURES)
            bootstrap_res, fixtures_res = await asyncio.gather(bootstrap_task, fixtures_task)
        bootstrap_res.raise_for_status()
        fixtures_res.raise_for_status()
    except httpx.RequestError as e:
        logging.error(f"❌ Failed to fetch live FPL data: {e}. Aborting update.")
        return

    bootstrap_data = bootstrap_res.json()
    fixtures_data = fixtures_res.json()

    is_game_live = any(gw.get('is_current', False) for gw in bootstrap_data['events'])
    current_gameweek_id = next((gw['id'] for gw in bootstrap_data['events'] if gw.get('is_current', False)), 1)
    logging.info(f"ℹ️ FPL game live status: {is_game_live}. Current GW: {current_gameweek_id}")

    teams_map = {team['id']: team['short_name'] for team in bootstrap_data['teams']}
    position_map = {p_type['id']: p_type['singular_name_short'] for p_type in bootstrap_data['element_types']}
    app.state.full_team_names = {team['short_name']: team['name'] for team in bootstrap_data['teams']}

    fpl_players_df = pd.DataFrame(bootstrap_data['elements'])
    fpl_players_df['team_name'] = fpl_players_df['team'].map(teams_map)
    fpl_players_df['position'] = fpl_players_df['element_type'].map(position_map)
    fpl_players_df = fpl_players_df.rename(columns={'web_name': 'Player'})

    fixtures_df = pd.DataFrame(fixtures_data)
    upcoming_fixtures_data = {}
    for team_id in teams_map.keys():
        team_fixtures = fixtures_df[((fixtures_df['team_h'] == team_id) | (fixtures_df['team_a'] == team_id)) & (fixtures_df['event'] >= current_gameweek_id)]
        fixtures_to_analyze = team_fixtures.head(5)
        fixture_details_list = []
        total_difficulty = 0
        for _, row in fixtures_to_analyze.iterrows():
            is_home = row['team_h'] == team_id
            opponent = teams_map.get(row['team_a'] if is_home else row['team_h'])
            difficulty = row['team_h_difficulty'] if is_home else row['team_a_difficulty']
            fixture_details_list.append({"gameweek": row.get("event"), "opponent": opponent, "is_home": is_home, "difficulty": difficulty})
            total_difficulty += difficulty
        avg_difficulty = total_difficulty / len(fixtures_to_analyze) if not fixtures_to_analyze.empty else 5.0
        upcoming_fixtures_data[team_id] = {"fixture_details": fixture_details_list, "avg_difficulty": round(avg_difficulty, 2)}

    fpl_players_df['fixture_details'] = fpl_players_df['team'].map(lambda tid: upcoming_fixtures_data.get(tid, {}).get('fixture_details'))
    fpl_players_df['avg_fixture_difficulty'] = fpl_players_df['team'].map(lambda tid: upcoming_fixtures_data.get(tid, {}).get('avg_difficulty'))

    if not FBREF_STATS_PATH.exists():
        logging.error("❌ FBref stats file not found. Player performance stats (xG, xA) will be missing.")
        fbref_df = pd.DataFrame()
    else:
        fbref_df = pd.read_csv(FBREF_STATS_PATH)

    if not fbref_df.empty:
        fpl_players_df['Player_lower'] = fpl_players_df['Player'].str.lower()
        fbref_df['Player_lower'] = fbref_df['Player'].str.lower()
        merged_df = pd.merge(fpl_players_df, fbref_df, on='Player_lower', how='left', suffixes=('', '_fbref'))
    else:
        merged_df = fpl_players_df
        
    merged_df.drop_duplicates(subset=['id'], keep='first', inplace=True)
    fbref_numeric_cols = ['Min_standard', 'Gls_standard', 'Ast_standard', 'xG_shooting', 'xAG_shooting', 'Sh_shooting', 'KP_passing', 'SCA_gca', 'Att Pen_possession']
    for col in fbref_numeric_cols:
        if col not in merged_df.columns:
            merged_df[col] = 0
        merged_df[col].fillna(0, inplace=True)

    merged_df.set_index('Player', inplace=True)
    master_fpl_data = merged_df
    app.state.last_data_update = pd.Timestamp.now().isoformat()
    logging.info("✅ Data update complete. Master DataFrame created.")

# --- App Lifecycle Events ---
@app.on_event("startup")
async def startup_event():
    DATA_DIR.mkdir(exist_ok=True)
    await load_and_process_all_data()
    scheduler.add_job(load_and_process_all_data, IntervalTrigger(hours=12))
    scheduler.start()
    logging.info("🚀 Server started and data refresh scheduler is running.")

@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown()
    logging.info("👋 Scheduler shut down.")

# --- CORS Middleware & Request Schema ---
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class Player(BaseModel): name: str; position: str; cost: float; team_name: str
class TeamData(BaseModel): players: List[Player]
class ChatMessage(BaseModel): role: str; text: str
class ChatRequest(BaseModel): team_id: int = None; question: str; history: List[ChatMessage] = Field(default_factory=list)

# --- API Endpoints ---
@app.get("/api/status")
async def get_status():
    return {"status": "ok", "is_game_live": is_game_live, "current_gameweek": current_gameweek_id, "last_data_update": app.state.last_data_update if hasattr(app.state, 'last_data_update') else None, "players_in_master_df": len(master_fpl_data) if master_fpl_data is not None else 0}

@app.get("/api/get-team-data/{team_id}", response_model=TeamData)
async def get_team_data(team_id: int):
    if master_fpl_data is None: raise HTTPException(status_code=503, detail="Data is not yet available.")
    if not is_game_live: raise HTTPException(status_code=400, detail="Cannot fetch team data during pre-season.")
    try:
        async with httpx.AsyncClient() as client:
            picks_url = FPL_API_TEAM_PICKS.format(team_id=team_id, gameweek=current_gameweek_id)
            picks_res = await client.get(picks_url)
            picks_res.raise_for_status()
            player_ids = [pick['element'] for pick in picks_res.json().get('picks', [])]
        team_df = master_fpl_data[master_fpl_data['id'].isin(player_ids)]
        players_list = [Player(name=index, position=player_row.position, cost=player_row.now_cost / 10.0, team_name=player_row.team_name) for index, player_row in team_df.iterrows()]
        return TeamData(players=players_list)
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=404, detail=f"Could not find FPL team for ID {team_id} in GW{current_gameweek_id}.")
    except Exception as e:
        logging.error(f"Error in get_team_data: {e}")
        raise HTTPException(status_code=500, detail="An unexpected server error occurred.")

# --- Context Builder ---
def _find_team_and_position(question_lower: str, full_team_names: dict) -> Tuple[str, str, str]:
    position_map = {
        'defenders': 'DEF', 'defender': 'DEF', 'defs': 'DEF', 'midfielders': 'MID', 'midfielder': 'MID', 'mids': 'MID',
        'forwards': 'FWD', 'forward': 'FWD', 'fwds': 'FWD', 'goalkeepers': 'GKP', 'goalkeeper': 'GKP', 'gk': 'GKP', 'gks': 'GKP'
    }
    team_found_short_name, pos_found_code, pos_found_str = None, None, None
    for short_name, full_name in full_team_names.items():
        if full_name.lower() in question_lower or short_name.lower() in question_lower:
            team_found_short_name = short_name; break
    for pos_str, pos_code in position_map.items():
        if pos_str in question_lower:
            pos_found_code, pos_found_str = pos_code, pos_str; break
    return team_found_short_name, pos_found_code, pos_found_str

def build_context_for_question(question: str, all_players_df: pd.DataFrame, full_team_names: dict) -> Tuple[str, List[str]]:
    question_lower = question.lower()
    
    # --- Intent 1: Specific Player Query (Corrected to handle duplicates) ---
    player_names_found = []
    cleaned_question = re.sub(r'\s+(or|vs)\s+', ' ', question_lower)
    cleaned_question = re.sub(r'[^a-z0-9\s]', '', cleaned_question)

    if 'simple_name' not in all_players_df.columns:
        all_players_df['simple_name'] = all_players_df.index.str.lower().str.replace(r'[^a-z0-9\s]', '', regex=True)

    # Use a vectorized approach for speed and to avoid manual loops
    matching_players_series = all_players_df['simple_name'].dropna().apply(lambda name: name in cleaned_question)
    
    if matching_players_series.any():
        player_names_found = all_players_df[matching_players_series].index.tolist()

    if player_names_found:
        return "", sorted(list(set(player_names_found)))

    # --- Intent 2: List all players from a specific team and/or position ---
    team_found, pos_found_code, _ = _find_team_and_position(question_lower, full_team_names)
    if team_found:
        df_filtered = all_players_df[all_players_df['team_name'] == team_found]
        if pos_found_code: df_filtered = df_filtered[df_filtered['position'] == pos_found_code]
        if not df_filtered.empty:
            pos_str = pos_found_code or 'Players'
            team_full_name = full_team_names.get(team_found, team_found)
            title = f"List of {team_full_name} {pos_str}"
            summary = f"\n--- {title} ---\n"
            for _, player in df_filtered.sort_values(by='now_cost', ascending=False).iterrows():
                summary += f"- {player.name} ({player.position}) - £{player.now_cost/10.0:.1f}m\n"
            return summary, []

    # --- Intent 3: Handle general "Top X" and fixture-based questions ---
    trigger_words = ['top', 'most', 'best', 'cheapest', 'worst', 'easiest', 'hardest', 'fixture', 'fixtures']
    if any(word in question_lower for word in trigger_words):
        limit_match = re.search(r'(\d+)', question_lower)
        limit = int(limit_match.group(1)) if limit_match else 5
        if 'fixture' in question_lower or 'fixtures' in question_lower:
            team_data = all_players_df[['team_name', 'avg_fixture_difficulty', 'fixture_details']].drop_duplicates(subset=['team_name'])
            ascending = 'easiest' in question_lower or 'best' in question_lower
            sorted_teams = team_data.sort_values(by='avg_fixture_difficulty', ascending=ascending).head(limit)
            title = f"Top {limit} Teams with {'Easiest' if ascending else 'Hardest'} Fixtures"
            summary = f"\n--- {title} ---\n"
            for _, team in sorted_teams.iterrows():
                fixtures_str = ", ".join([f"{f['opponent']} ({'H' if f['is_home'] else 'A'})" for f in team['fixture_details']])
                summary += f"- {full_team_names.get(team['team_name'])} (Avg Diff: {team['avg_fixture_difficulty']}): {fixtures_str}\n"
            return summary, []
        df_filtered = all_players_df.copy()
        _, pos_found_code, pos_found_str = _find_team_and_position(question_lower, full_team_names)
        if pos_found_code: df_filtered = df_filtered[df_filtered['position'] == pos_found_code]
        sort_by, metric_str, ascending = ('now_cost', "Most Expensive", False)
        if "cheap" in question_lower: sort_by, metric_str, ascending = 'now_cost', "Cheapest", True
        elif "selected" in question_lower or "ownership" in question_lower: sort_by, metric_str = 'selected_by_percent', "Most Selected"
        elif "form" in question_lower: sort_by, metric_str = 'form', "Best Form"
        elif "points" in question_lower: sort_by, metric_str = 'total_points', "Highest Scoring"
        df_filtered[sort_by] = pd.to_numeric(df_filtered[sort_by], errors='coerce')
        df_filtered.dropna(subset=[sort_by], inplace=True)
        top_players = df_filtered.sort_values(by=sort_by, ascending=ascending).head(limit)
        title = f"Top {limit} {metric_str} {pos_found_str or 'Players'}"
        summary = f"\n--- {title} ---\n"
        for _, player in top_players.iterrows():
            value = player[sort_by]
            display_val = f"£{value/10.0:.1f}m" if sort_by == 'now_cost' else f"{value}%" if sort_by == 'selected_by_percent' else value
            summary += f"- {player.name} ({player.team_name}, {player.position}) - {display_val}\n"
        return summary, []

    return "", []

# --- Main Chat Endpoint ---
@app.post("/api/chat")
async def chat_with_bot(request: ChatRequest):
    return StreamingResponse(stream_chat_response(request), media_type="text/event-stream")

async def stream_chat_response(request: ChatRequest):
    if master_fpl_data is None:
        yield "data: Sorry, the FPL data is not available. The server may still be initializing. Please try again in a moment.\n\n"
        return

    try:
        full_conversation_text = " ".join([h.text for h in request.history]) + " " + request.question
        general_summary, players_from_question = build_context_for_question(full_conversation_text, master_fpl_data, app.state.full_team_names)
        
        context_block = ""
        if players_from_question:
            if 'upcoming_fixtures' not in master_fpl_data.columns:
                 master_fpl_data['upcoming_fixtures'] = master_fpl_data['fixture_details'].apply(
                    lambda details: ", ".join([f"{f['opponent']} ({'H' if f['is_home'] else 'A'}) (D:{f['difficulty']})" for f in details]) if isinstance(details, list) else ""
                )
            if len(players_from_question) > 1:
                 context_block += "Found multiple players matching your query. Here is the data for all of them:\n"
            for name in players_from_question:
                if name in master_fpl_data.index:
                    player = master_fpl_data.loc[name]
                    if isinstance(player, pd.DataFrame): player = player.iloc[0]
                    context_block += f"\n--- Player Details: {player.name} ---\n"
                    context_block += f"Team: {player.team_name}, Position: {player.position}\n"
                    context_block += f"Price: £{player.now_cost/10.0:.1f}m, Selected By: {player.selected_by_percent}%, Form: {player.form}\n"
                    context_block += f"News: {player.news if player.news else 'No issues reported.'}\n"
                    context_block += f"FPL Stats (Total): Points: {player.total_points}, Bonus: {player.bonus}, ICT Index: {player.ict_index}\n"
                    context_block += f"FBref Stats (Per 90): xG: {player.get('xG_shooting', 'N/A')}, xAG: {player.get('xAG_shooting', 'N/A')}, Shots: {player.get('Sh_shooting', 'N/A')}\n"
                    context_block += f"Upcoming Fixtures: {player.upcoming_fixtures}\n"
            context_block += "---\n"
        elif general_summary:
            context_block = general_summary
        else:
            context_block = "I couldn't find specific data for your query. Please try rephrasing your question or asking about a specific player, team, or position."

        gemini_history = [{"role": "model" if h.role == "bot" else "user", "parts": [{"text": h.text}]} for h in request.history]

        async for chunk in gemini_service.get_ai_response_stream(request.question, gemini_history, context_block, is_game_live):
            yield chunk

    except Exception as e:
        logging.error(f"Error during chat streaming: {e}")
        yield f"data: Sorry, I encountered a critical server error. Please check the server logs for details.\n\n"