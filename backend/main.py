# backend/main.py

import os
import httpx
import google.generativeai as genai
import asyncio 
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

# --- FPL API URLs ---
FPL_API_BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_API_TEAM_PICKS = "https://fantasy.premierleague.com/api/entry/{team_id}/event/{gameweek}/picks/"

# --- Cache Setup ---
fpl_bootstrap_cache = TTLCache(maxsize=1, ttl=21600)

# --- FastAPI App Initialization ---
app = FastAPI(
    title="FPL AI Chatbot API",
    description="API for fetching FPL data and interacting with an AI chatbot.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Models ---
class ChatRequest(BaseModel):
    team_id: int = Field(..., description="The user's FPL team ID.")
    question: str = Field(..., description="The user's question for the chatbot.")

class Player(BaseModel):
    name: str
    position: str
    cost: float

class TeamData(BaseModel):
    team_id: int
    gameweek: int
    players: list[Player]

# --- Helper function to get bootstrap data (with caching) ---
async def get_bootstrap_data():
    if 'bootstrap_data' in fpl_bootstrap_cache:
        print("CACHE HIT: Returning cached bootstrap data.")
        return fpl_bootstrap_cache['bootstrap_data']
    
    print("CACHE MISS: Fetching new bootstrap data from FPL API.")
    async with httpx.AsyncClient() as client:
        bootstrap_res = await client.get(FPL_API_BOOTSTRAP)
        bootstrap_res.raise_for_status()
        bootstrap_data = bootstrap_res.json()
        fpl_bootstrap_cache['bootstrap_data'] = bootstrap_data
        return bootstrap_data

# --- API Endpoints ---

@app.get("/")
def read_root():
    return {"message": "Welcome to the FPL AI Chatbot API"}

@app.get("/api/get-team-data/{team_id}", response_model=TeamData)
async def get_team_data(team_id: int):
    try:
        bootstrap_data = await get_bootstrap_data()
        current_gameweek = next((gw['id'] for gw in bootstrap_data['events'] if gw['is_current']), 1)
        player_map = {p['id']: {'name': p['web_name'], 'cost': p['now_cost'] / 10} for p in bootstrap_data['elements']}
        position_map = {p_type['id']: p_type['singular_name_short'] for p_type in bootstrap_data['element_types']}
        
        team_picks_url = FPL_API_TEAM_PICKS.format(team_id=team_id, gameweek=current_gameweek)
        async with httpx.AsyncClient() as client:
            picks_res = await client.get(team_picks_url)
        
        if picks_res.status_code == 404:
             return TeamData(team_id=team_id, gameweek=current_gameweek, players=[])

        picks_res.raise_for_status()
        picks_data = picks_res.json()

        players = []
        for pick in picks_data['picks']:
            player_id = pick['element']
            player_details = player_map.get(player_id)
            player_type_id = next((p['element_type'] for p in bootstrap_data['elements'] if p['id'] == player_id), None)
            position = position_map.get(player_type_id, 'N/A')

            if player_details:
                players.append(Player(name=player_details['name'], position=position, cost=player_details['cost']))
        
        return TeamData(team_id=team_id, gameweek=current_gameweek, players=players)

    except httpx.HTTPStatusError:
        raise HTTPException(status_code=404, detail=f"Could not find FPL data for Team ID {team_id}. Please check the ID.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


async def stream_chat_response(request: ChatRequest):
    """
    An async generator function that yields chunks of the AI's response.
    """
    try:
        team_data = await get_team_data(request.team_id)

        # --- THE FIX ---
        # Changed `team_data.json()` to `team_data.model_dump_json()` for Pydantic V2 compatibility.
        prompt = f"""
        You are an expert Fantasy Premier League (FPL) assistant.
        A user is asking for advice about their team.

        Here is the user's current team data for Gameweek {team_data.gameweek}:
        {team_data.model_dump_json(indent=2)}

        Here is the user's question: "{request.question}"

        Please provide a helpful, friendly, and concise response.
        Analyze the team in the context of their question.
        Keep your answer to a few sentences.
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
    """
    Handles the chat request by returning a streaming response.
    """
    return StreamingResponse(stream_chat_response(request), media_type="text/event-stream")
