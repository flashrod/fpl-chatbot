import os
import httpx
import google.generativeai as genai
import asyncio
import pandas as pd
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi.responses import StreamingResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

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
# CHANGE 1: Add a flag to track if the FPL game is live
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

    # CHANGE 2: Determine if any gameweek is 'current'
    is_game_live = any(gw.get('is_current', False) for gw in bootstrap_data['events'])
    current_gameweek_id = next((gw['id'] for gw in bootstrap_data['events'] if gw.get('is_current', False)), 1)
    print(f"ℹ️ FPL game live status: {is_game_live}. Current GW: {current_gameweek_id}")

    # (The rest of the data processing remains the same)
    teams_map = {team['id']: team['short_name'] for team in bootstrap_data['teams']}
    fpl_players_df = pd.DataFrame(bootstrap_data['elements'])
    fpl_players_df['team_name'] = fpl_players_df['team'].map(teams_map)
    fpl_players_df = fpl_players_df.rename(columns={'web_name': 'Player'})
    fixtures_df = pd.DataFrame(fixtures_data)
    upcoming_fixtures = {}
    for team_id in teams_map.keys():
        team_fixtures = fixtures_df[((fixtures_df['team_h'] == team_id) | (fixtures_df['team_a'] == team_id)) & (fixtures_df['event'] >= current_gameweek_id)]
        fixture_strings = []
        for _, row in team_fixtures.head(5).iterrows():
            opponent = teams_map[row['team_a']] if row['team_h'] == team_id else teams_map[row['team_h']]
            venue = "(H)" if row['team_h'] == team_id else "(A)"
            difficulty = row['team_h_difficulty'] if row['team_h'] == team_id else row['team_a_difficulty']
            fixture_strings.append(f"{opponent} {venue} [{difficulty}]")
        upcoming_fixtures[team_id] = ", ".join(fixture_strings)
    fpl_players_df['upcoming_fixtures'] = fpl_players_df['team'].map(upcoming_fixtures)
    
    if not FBREF_STATS_PATH.exists():
        print("❌ FBref stats file not found. Run data_pipeline.py first. Aborting update.")
        return
    fbref_df = pd.read_csv(FBREF_STATS_PATH)
    fpl_players_df['Player_lower'] = fpl_players_df['Player'].str.lower()
    fbref_df['Player_lower'] = fbref_df['Player'].str.lower()
    merged_df = pd.merge(fpl_players_df, fbref_df, on='Player_lower', how='left')
    merged_df.set_index('Player_x', inplace=True)
    master_fpl_data = merged_df
    print("✅ Data update complete. Master DataFrame created.")

# (Startup/Shutdown events remain the same)
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    team_id: int
    question: str

# --- API Endpoints ---
async def stream_chat_response(request: ChatRequest):
    if master_fpl_data is None:
        yield "Sorry, the FPL data is not available. The server may still be initializing. Please try again in a moment."
        return

    player_ids = []
    user_notes = "" # A place to store messages for the user

    # CHANGE 3: Graceful handling of team pick fetching
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
                    # For other errors like 500, 503, etc.
                    user_notes += "(Note: There was a temporary issue fetching your FPL team.)\n"
        except Exception as e:
            print(f"Error fetching picks: {e}")
            user_notes += "(Note: An unexpected error occurred while fetching your FPL team.)\n"
    else:
        user_notes += "(Note: The FPL game is currently between seasons, so I can't fetch your team. You can still ask general player questions.)\n"

    # Now, the code continues gracefully even if picks failed
    try:
        player_names = master_fpl_data[master_fpl_data['id'].isin(player_ids)].index.tolist()
        
        # Add players from the question itself for general queries
        for name in master_fpl_data.index:
            if isinstance(name, str) and name.lower() in request.question.lower() and name not in player_names:
                player_names.append(name)

        context_block = f"\n\n--- Player Analysis ---\n{user_notes}\n"
        for name in sorted(list(set(player_names))):
            if name in master_fpl_data.index:
                player = master_fpl_data.loc[name]
                context_block += f"**{player.name}** ({player.team_name})\n"
                fpl_context = f"  - **FPL Status:** Price: £{player.now_cost/10.0:.1f}, Form: {player.form}, Selected: {player.selected_by_percent}%, News: {player.news or 'Available'}\n"
                fbref_context = f"  - **Season Stats:** Mins: {int(player.get('Min_standard', 0))}, xG: {round(player.get('xG_shooting', 0), 2)}, xAG: {round(player.get('xAG_shooting', 0), 2)}, SCA: {int(player.get('SCA_gca', 0))}\n"
                fixture_context = f"  - **Upcoming Fixtures:** {player.upcoming_fixtures}\n"
                context_block += fpl_context + fbref_context + fixture_context

        # (The prompt remains the same)
        prompt = f"""
        You are "FPL Brain", the world's most advanced Fantasy Premier League analyst. You have access to a complete dataset combining live FPL data and deep performance stats.
        Your task is to provide expert advice by synthesizing all available information.

        **Reasoning Hierarchy:**
        1.  **Availability is Key:** If a player has injury **News**, this is the most important factor.
        2.  **Fixtures Drive Short-Term Decisions:** Use the **Upcoming Fixtures** (with difficulty scores) to recommend immediate transfers. Easy fixtures are a huge plus.
        3.  **Underlying Stats (xG/xAG) Predict Future Returns:** Use a player's **Season Stats** to determine if their FPL **Form** is sustainable. A player with high xG and low Form is a great target. A player with high Form but low xG might be getting lucky.
        4.  **Price and Ownership as Context:** Use **Price** and **Selected By %** to assess value and risk. A cheap, low-ownership player with good stats and fixtures is a differential gem.
        5.  **Acknowledge Missing Data:** If you see a note about not being able to fetch the user's team, incorporate that into your answer gracefully.

        ---
        **User's Question:** "{request.question}"
        
        **Analysis of User's Players:**
        {context_block}
        ---
        
        Now, provide your expert, multi-faceted FPL recommendation.
        """

        model = genai.GenerativeModel('gemini-1.5-flash')
        response_stream = await model.generate_content_async(prompt, stream=True)
        async for chunk in response_stream:
            if chunk.text:
                yield chunk.text
    except Exception as e:
        print(f"Error during chat streaming: {e}")
        yield "Sorry, I encountered a critical error. Please try again."

@app.post("/api/chat")
async def chat_with_bot(request: ChatRequest):
    return StreamingResponse(stream_chat_response(request), media_type="text/event-stream")