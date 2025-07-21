import os
import httpx
import asyncio
import pandas as pd
from pathlib import Path
from typing import List
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi.responses import StreamingResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import google.generativeai as genai
import chip_service

# --- Configuration ---
load_dotenv()
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
    """
    The main data processing function. Fetches from FPL API and FBref,
    then merges them into a single master DataFrame.
    """
    global master_fpl_data, current_gameweek_id, is_game_live
    print("🔄 Starting data update process...")

    async with httpx.AsyncClient() as client:
        bootstrap_task = client.get(FPL_API_BOOTSTRAP)
        fixtures_task = client.get(FPL_API_FIXTURES)
        bootstrap_res, fixtures_res = await asyncio.gather(bootstrap_task, fixtures_task)

    if bootstrap_res.status_code != 200 or fixtures_res.status_code != 200:
        print("❌ Failed to fetch live FPL data. Aborting update.")
        return

    bootstrap_data = bootstrap_res.json()
    fixtures_data = fixtures_res.json()
    
    # --- DEBUGGING: Print a sample of the raw player data from the API ---
    print("\n--- DEBUG: Sample Raw Player Data from FPL API ---")
    if bootstrap_data.get('elements'):
        print(json.dumps(bootstrap_data['elements'][0], indent=2))
    else:
        print("No 'elements' key found in bootstrap data.")
    # --- END DEBUGGING ---

    is_game_live = any(gw.get('is_current', False) for gw in bootstrap_data['events'])
    current_gameweek_id = next((gw['id'] for gw in bootstrap_data['events'] if gw.get('is_current', False)), 1)
    print(f"ℹ️ FPL game live status: {is_game_live}. Current GW: {current_gameweek_id}")

    teams_map = {team['id']: team['short_name'] for team in bootstrap_data['teams']}
    position_map = {p_type['id']: p_type['singular_name_short'] for p_type in bootstrap_data['element_types']}

    fpl_players_df = pd.DataFrame(bootstrap_data['elements'])
    fpl_players_df['team_name'] = fpl_players_df['team'].map(teams_map)
    fpl_players_df['position'] = fpl_players_df['element_type'].map(position_map)
    fpl_players_df = fpl_players_df.rename(columns={'web_name': 'Player'})
    
    # --- DEBUGGING: Check player names as they appear in the DataFrame ---
    print("\n--- DEBUG: Checking for 'Salah' in Player Names from API ---")
    salah_in_df = 'Salah' in fpl_players_df['Player'].values
    print(f"Is 'Salah' an exact match in the 'Player' column? -> {salah_in_df}")
    if not salah_in_df:
        print("Could not find exact match for 'Salah'. Searching for partial match...")
        salah_partial = fpl_players_df[fpl_players_df['Player'].str.contains("Salah", case=False)]
        if not salah_partial.empty:
            print("Found partial match(es):")
            print(salah_partial[['Player', 'team_name']].to_dict('records'))
        else:
            print("Could not find any partial match for 'Salah' either.")
            print("First 20 player names from API for review:")
            print(fpl_players_df['Player'].head(20).tolist())
    print("--- END DEBUGGING ---\n")
    # --- END DEBUGGING ---


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
            opponent = teams_map[row['team_a'] if is_home else row['team_h']]
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

    fpl_players_df['fixture_details'] = fpl_players_df['team'].map(lambda tid: upcoming_fixtures_data.get(tid, {}).get('fixture_details'))
    fpl_players_df['avg_fixture_difficulty'] = fpl_players_df['team'].map(lambda tid: upcoming_fixtures_data.get(tid, {}).get('avg_difficulty'))

    if not FBREF_STATS_PATH.exists():
        print("❌ FBref stats file not found. Run data_pipeline.py first. Aborting update.")
        return

    fbref_df = pd.read_csv(FBREF_STATS_PATH)
    fpl_players_df['Player_lower'] = fpl_players_df['Player'].str.lower()
    fbref_df['Player_lower'] = fbref_df['Player'].str.lower()
    merged_df = pd.merge(fpl_players_df, fbref_df, on='Player_lower', how='left')

    fbref_numeric_cols = [
        'Min_standard', 'Gls_standard', 'Ast_standard', 'xG_shooting', 
        'xAG_shooting', 'Sh_shooting', 'KP_passing', 'SCA_gca', 'Att Pen_possession'
    ]
    for col in fbref_numeric_cols:
        if col in merged_df.columns:
            merged_df[col].fillna(0, inplace=True)

    merged_df.set_index('Player_x', inplace=True)
    master_fpl_data = merged_df
    print("✅ Data update complete. Master DataFrame created.")

# --- App Lifecycle Events ---
@app.on_event("startup")
async def startup_event():
    await load_and_process_all_data()
    scheduler.add_job(load_and_process_all_data, IntervalTrigger(days=3))
    scheduler.start()
    print("🚀 Server started and data refresh scheduler is running.")

@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown()
    print("👋 Scheduler shut down.")

# --- CORS Middleware & Request Schema ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Player(BaseModel):
    name: str
    position: str
    cost: float
    team_name: str

class TeamData(BaseModel):
    players: List[Player]

class ChatRequest(BaseModel):
    team_id: int
    question: str

# --- API Endpoints ---
@app.get("/api/fixture-difficulty")
async def get_fixture_difficulty_data():
    return chip_service.get_all_team_fixture_difficulty(master_fpl_data)

@app.get("/api/chip-recommendations")
async def get_chip_recommendations_data():
    return chip_service.calculate_chip_recommendations(master_fpl_data)

@app.get("/api/get-team-data/{team_id}", response_model=TeamData)
async def get_team_data(team_id: int):
    if master_fpl_data is None or not is_game_live:
        return TeamData(players=[])

    try:
        async with httpx.AsyncClient() as client:
            picks_url = FPL_API_TEAM_PICKS.format(team_id=team_id, gameweek=current_gameweek_id)
            picks_res = await client.get(picks_url)
            
            if picks_res.status_code != 200:
                raise HTTPException(status_code=404, detail=f"Could not find a team for ID {team_id} in the current gameweek.")
            
            player_ids = [pick['element'] for pick in picks_res.json().get('picks', [])]

        team_df = master_fpl_data[master_fpl_data['id'].isin(player_ids)]
        
        players_list = []
        for index, player_row in team_df.iterrows():
            players_list.append(Player(
                name=player_row.name,
                position=player_row.position,
                cost=player_row.now_cost / 10.0,
                team_name=player_row.team_name
            ))
        
        return TeamData(players=players_list)

    except Exception as e:
        print(f"Error in get_team_data: {e}")
        raise HTTPException(status_code=500, detail="An unexpected server error occurred.")


@app.post("/api/chat")
async def chat_with_bot(request: ChatRequest):
    return StreamingResponse(stream_chat_response(request), media_type="text/event-stream")

async def stream_chat_response(request: ChatRequest):
    if master_fpl_data is None:
        yield "Sorry, the FPL data is not available. The server may still be initializing. Please try again in a moment."
        return

    player_ids = []
    user_notes = ""

    if is_game_live:
        try:
            async with httpx.AsyncClient() as client:
                picks_url = FPL_API_TEAM_PICKS.format(team_id=request.team_id, gameweek=current_gameweek_id)
                picks_res = await client.get(picks_url)
                if picks_res.status_code == 200:
                    player_ids = [pick['element'] for pick in picks_res.json().get('picks', [])]
                elif picks_res.status_code == 404:
                    user_notes += "(Note: Could not fetch your team. The Team ID might be incorrect or you haven't picked a team for this gameweek yet.)\n"
                else:
                    user_notes += "(Note: There was a temporary issue fetching your FPL team.)\n"
        except Exception as e:
            print(f"Error fetching picks: {e}")
            user_notes += "(Note: An unexpected error occurred while fetching your FPL team.)\n"
    else:
        user_notes += "(Note: The FPL game is currently in pre-season, so I can't fetch your specific team. You can still ask general player questions.)\n"

    try:
        player_names = master_fpl_data[master_fpl_data['id'].isin(player_ids)].index.tolist()

        for name in master_fpl_data.index:
            if isinstance(name, str) and name.lower() in request.question.lower() and name not in player_names:
                player_names.append(name)

        context_block = f"\n\n--- Player Analysis ---\n{user_notes}\n"
        master_fpl_data['upcoming_fixtures'] = master_fpl_data['fixture_details'].apply(
            lambda details: ", ".join([f"{f['opponent']} ({'H' if f['is_home'] else 'A'}) [{f['difficulty']}]" for f in details]) if isinstance(details, list) else ""
        )
        for name in sorted(list(set(player_names))):
            if name in master_fpl_data.index:
                player = master_fpl_data.loc[name]
                context_block += f"**{player.name}** ({player.team_name})\n"
                fpl_context = (
                    f"  - **FPL Status:** Price: £{player.now_cost/10.0:.1f}, "
                    f"Form: {player.form}, Selected: {player.selected_by_percent}%, "
                    f"News: {player.news or 'Available'}\n"
                )
                fbref_context = (
                    f"  - **Season Stats:** Mins: {int(player.get('Min_standard', 0))}, "
                    f"xG: {round(player.get('xG_shooting', 0), 2)}, "
                    f"xAG: {round(player.get('xAG_shooting', 0), 2)}, "
                    f"SCA: {int(player.get('SCA_gca', 0))}\n"
                )
                fixture_context = f"  - **Upcoming Fixtures:** {player.upcoming_fixtures}\n"
                context_block += fpl_context + fbref_context + fixture_context
        
        # --- NEW: More Forceful and Specific Prompt Instructions ---
        if not is_game_live:
            system_instruction = """
            **IMPORTANT: You are in PRE-SEASON mode.**
            Your task is to evaluate a player's value based on the data provided in the "Player Analysis" section.
            
            **Instructions:**
            1.  Find the player mentioned in the user's question within the "Player Analysis" block.
            2.  Extract their **Price** from the "FPL Status" line.
            3.  Extract their team's opening games from the "Upcoming Fixtures" line.
            4.  Formulate your answer based ONLY on this price and fixture information. Acknowledge that performance stats (xG, goals) are not available yet because no matches have been played.
            5.  **DO NOT state that you don't have the player's information if they are listed in the data below.** You must use the data provided.
            """
        else:
            system_instruction = """
            **Reasoning Hierarchy:**
            1.  **Availability is Key:** If a player has injury **News**, this is the most important factor.
            2.  **Fixtures Drive Short-Term Decisions:** Use the **Upcoming Fixtures** (with difficulty scores) to recommend immediate transfers.
            3.  **Underlying Stats (xG/xAG) Predict Future Returns:** Use a player's **Season Stats** to determine if their FPL **Form** is sustainable.
            4.  **Price and Ownership as Context:** Use **Price** and **Selected By %** to assess value and risk.
            """

        prompt = f"""
        You are "FPL Brain", the world's most advanced Fantasy Premier League analyst.
        
        {system_instruction}

        ---
        **User's Question:** "{request.question}"
        **Analysis of Available Player Data:**
        {context_block}
        ---
        
        Now, provide your expert, multi-faceted FPL recommendation.
        """

        model = genai.GenerativeModel('gemini-2.0-flash')
        response_stream = await model.generate_content_async(prompt, stream=True)

        async for chunk in response_stream:
            if chunk.text:
                yield chunk.text

    except Exception as e:
        print(f"Error during chat streaming: {e}")
        yield "Sorry, I encountered a critical error. Please try again."
