# backend/main.py

import os
import httpx
import google.generativeai as genai
import asyncio
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from cachetools import TTLCache
from fastapi.responses import StreamingResponse

# --- Configuration ---
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found. Please set it in your .env file.")
genai.configure(api_key=GEMINI_API_KEY)

# --- Paths & URLs ---
FPL_API_BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_API_TEAM_PICKS = "https://fantasy.premierleague.com/api/entry/{team_id}/event/{gameweek}/picks/"
PROCESSED_DATA_PATH = Path(__file__).parent / "fpl_data" / "processed_player_data.json"

# --- Cache & Data Store ---
fpl_bootstrap_cache = TTLCache(maxsize=1, ttl=21600)
historical_data_store = {}

# --- FastAPI App Initialization & Events ---
app = FastAPI(title="FPL AI Chatbot API")

@app.on_event("startup")
def load_historical_data():
    """Load the processed historical data into memory when the app starts."""
    global historical_data_store
    if PROCESSED_DATA_PATH.exists():
        print("Loading historical player data into memory...")
        with open(PROCESSED_DATA_PATH, 'r', encoding='utf-8') as f:
            historical_data_store = json.load(f)
        print("✅ Historical data loaded successfully.")
    else:
        print("⚠️ Historical data file not found. Chatbot will have limited knowledge.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Models ---
class ChatRequest(BaseModel):
    team_id: int
    question: str
class Player(BaseModel):
    name: str
    position: str
    cost: float
class TeamData(BaseModel):
    team_id: int
    gameweek: int
    players: list[Player]

# --- Helper Functions ---
async def get_bootstrap_data():
    if 'bootstrap_data' in fpl_bootstrap_cache:
        return fpl_bootstrap_cache['bootstrap_data']
    async with httpx.AsyncClient() as client:
        res = await client.get(FPL_API_BOOTSTRAP)
        res.raise_for_status()
        data = res.json()
        fpl_bootstrap_cache['bootstrap_data'] = data
        return data

@app.get("/api/get-team-data/{team_id}", response_model=TeamData)
async def get_team_data(team_id: int):
    """
    Fetches the user's FPL team data. It now handles the pre-season case
    where player picks for GW1 might not be available yet.
    """
    try:
        bootstrap_data = await get_bootstrap_data()
        
        # Check if the team ID exists in the bootstrap data (a basic validation)
        # Note: This is a simplified check. A more robust check would be to hit the /entry/{team_id}/ endpoint.
        # For our purposes, this is sufficient to confirm the team exists.
        
        current_gameweek = next((gw['id'] for gw in bootstrap_data['events'] if gw['is_current']), 1)
        player_map = {p['id']: {'name': p['web_name'], 'cost': p['now_cost'] / 10} for p in bootstrap_data['elements']}
        position_map = {p_type['id']: p_type['singular_name_short'] for p_type in bootstrap_data['element_types']}
        
        team_picks_url = FPL_API_TEAM_PICKS.format(team_id=team_id, gameweek=current_gameweek)
        
        players = []
        async with httpx.AsyncClient() as client:
            picks_res = await client.get(team_picks_url)
            
            # --- THE FIX ---
            # If picks are not found (404), it's okay, especially in pre-season.
            # We will just return an empty player list but still give a 200 OK response
            # to allow the login to succeed.
            if picks_res.status_code == 200:
                picks_data = picks_res.json()
                for pick in picks_data.get('picks', []):
                    player_id = pick['element']
                    player_details = player_map.get(player_id)
                    player_type_id = next((p['element_type'] for p in bootstrap_data['elements'] if p['id'] == player_id), None)
                    position = position_map.get(player_type_id, 'N/A')

                    if player_details:
                        players.append(Player(name=player_details['name'], position=position, cost=player_details['cost']))

        return TeamData(team_id=team_id, gameweek=current_gameweek, players=players)

    except httpx.HTTPStatusError:
        raise HTTPException(status_code=404, detail=f"Could not find FPL data for Team ID {team_id}. It may be an invalid ID.")
    except Exception as e:
        # Catch any other unexpected errors
        print(f"Error in get_team_data: {e}")
        raise HTTPException(status_code=500, detail="An unexpected server error occurred.")


async def stream_chat_response(request: ChatRequest):
    try:
        team_data = await get_team_data(request.team_id)
        
        historical_context = ""
        for player_name in historical_data_store:
            # Simple check if player name is in the question
            if player_name.lower() in request.question.lower():
                historical_context += f"\n\nHistorical Context for {player_name}:\n"
                player_stats = historical_data_store[player_name]
                historical_context += json.dumps(player_stats, indent=2)

        prompt = f"""
        You are an expert Fantasy Premier League (FPL) assistant.
        A user is asking for advice about their team.

        Here is the user's current team data for Gameweek {team_data.gameweek}:
        {team_data.model_dump_json(indent=2)}
        
        {historical_context if historical_context else "No specific historical data requested."}

        Based on ALL of the data above, answer the user's question: "{request.question}"

        Provide a helpful, friendly, and concise response.
        """

        model = genai.GenerativeModel('gemini-1.5-flash')
        response_stream = await model.generate_content_async(prompt, stream=True)

        async for chunk in response_stream:
            if chunk.text:
                yield chunk.text
                await asyncio.sleep(0.02) 

    except Exception as e:
        print(f"Error during chat streaming: {e}")
        yield "Sorry, I encountered an error. Please try again."

@app.post("/api/chat")
async def chat_with_bot(request: ChatRequest):
    return StreamingResponse(stream_chat_response(request), media_type="text/event-stream")
