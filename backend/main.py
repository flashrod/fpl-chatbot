# backend/main.py

import os
import httpx
import google.generativeai as genai
import asyncio
import json
from pathlib import Path
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
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
    raise ValueError("GEMINI_API_KEY not found in .env file.")
genai.configure(api_key=GEMINI_API_KEY)

# --- Paths & URLs ---
FPL_API_BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_API_FIXTURES = "https://fantasy.premierleague.com/api/fixtures/"
FPL_API_TEAM_PICKS = "https://fantasy.premierleague.com/api/entry/{team_id}/event/{gameweek}/picks/"
DATA_DIR = Path(__file__).parent / "fpl_data"
PROCESSED_DATA_PATH = DATA_DIR / "processed_player_data.json"
FAISS_INDEX_PATH = DATA_DIR / "player_data.index"

# --- In-Memory Stores ---
fpl_live_data_cache = TTLCache(maxsize=1, ttl=3600) # Cache live data for 1 hour
historical_data_store = {}
vector_index = None
embedding_model = None
player_id_map = {}

# --- FastAPI App Initialization & Events ---
app = FastAPI(title="FPL AI Chatbot API")

@app.on_event("startup")
def load_data_and_models():
    """Load all necessary data and models into memory when the app starts."""
    global historical_data_store, vector_index, embedding_model, player_id_map
    if PROCESSED_DATA_PATH.exists():
        print("Loading historical player data...")
        with open(PROCESSED_DATA_PATH, 'r', encoding='utf-8') as f:
            historical_data_store = json.load(f)
        player_id_map = {i: name for i, name in enumerate(historical_data_store.keys())}
        print("✅ Historical data loaded.")
    else:
        print("⚠️ Historical data file not found.")

    print("Loading sentence transformer model...")
    embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    print("✅ Embedding model loaded.")

    if FAISS_INDEX_PATH.exists():
        print("Loading FAISS vector index...")
        vector_index = faiss.read_index(str(FAISS_INDEX_PATH))
        print("✅ FAISS index loaded.")
    else:
        print("⚠️ FAISS index not found. RAG will not be available.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# (Pydantic Models remain the same)
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

async def get_live_fpl_data():
    """
    Gets live FPL data (bootstrap, fixtures, injuries) using a cache.
    This is an upgrade that combines multiple data sources.
    """
    if 'live_data' in fpl_live_data_cache:
        print("CACHE HIT: Returning cached live FPL data.")
        return fpl_live_data_cache['live_data']
    
    print("CACHE MISS: Fetching new live data from FPL API.")
    async with httpx.AsyncClient() as client:
        # Fetch bootstrap and fixtures data concurrently
        bootstrap_task = client.get(FPL_API_BOOTSTRAP)
        fixtures_task = client.get(FPL_API_FIXTURES)
        bootstrap_res, fixtures_res = await asyncio.gather(bootstrap_task, fixtures_task)
        
        bootstrap_res.raise_for_status()
        fixtures_res.raise_for_status()
        
        bootstrap_data = bootstrap_res.json()
        fixtures_data = fixtures_res.json()

        # --- Process the data to make it more useful ---
        teams_map = {team['id']: team['short_name'] for team in bootstrap_data['teams']}
        
        # Process injuries and form
        player_details = {}
        for p in bootstrap_data['elements']:
            player_details[p['id']] = {
                'name': p['web_name'],
                'team_id': p['team'],
                'status': p['status'],
                'news': p['news'],
                'form': p['form']
            }
        
        # Process upcoming fixtures
        upcoming_fixtures = {}
        current_gameweek = next((gw['id'] for gw in bootstrap_data['events'] if gw['is_current']), None)
        if current_gameweek:
            for team_id in teams_map:
                team_fixtures = [
                    f"{teams_map[f['team_a']]} (A) [{f['difficulty']}]" if f['team_h'] != team_id else f"{teams_map[f['team_h']]} (H) [{f['difficulty']}]"
                    for f in fixtures_data 
                    if (f['team_h'] == team_id or f['team_a'] == team_id) and f['event'] and f['event'] >= current_gameweek
                ]
                upcoming_fixtures[teams_map[team_id]] = team_fixtures[:3] # Get the next 3 fixtures

        live_data = {
            "bootstrap": bootstrap_data,
            "player_details": player_details,
            "upcoming_fixtures": upcoming_fixtures
        }
        fpl_live_data_cache['live_data'] = live_data
        return live_data

async def get_team_data(team_id: int):
    try:
        live_data = await get_live_fpl_data()
        bootstrap_data = live_data['bootstrap']
        
        current_gameweek = next((gw['id'] for gw in bootstrap_data['events'] if gw['is_current']), 1)
        player_map = {p['id']: {'name': p['web_name'], 'cost': p['now_cost'] / 10} for p in bootstrap_data['elements']}
        position_map = {p_type['id']: p_type['singular_name_short'] for p_type in bootstrap_data['element_types']}
        
        team_picks_url = FPL_API_TEAM_PICKS.format(team_id=team_id, gameweek=current_gameweek)
        
        players = []
        async with httpx.AsyncClient() as client:
            picks_res = await client.get(team_picks_url)
            
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- RAG-Powered Chat Stream ---
async def stream_chat_response(request: ChatRequest):
    try:
        team_data = await get_team_data(request.team_id)
        live_data = await get_live_fpl_data()

        # --- RAG IMPLEMENTATION ---
        historical_context = ""
        if vector_index and embedding_model:
            print("Performing RAG search...")
            question_embedding = embedding_model.encode([request.question])
            k = 3
            distances, indices = vector_index.search(question_embedding, k)
            
            retrieved_players = set()
            for i in indices[0]:
                if i != -1:
                    player_name = player_id_map.get(i)
                    if player_name:
                        retrieved_players.add(player_name)
            
            if retrieved_players:
                historical_context += "\n\n--- Relevant Historical & Live Context ---\n"
                for name in retrieved_players:
                    historical_context += f"Player: {name}\n"
                    # Add historical data
                    if name in historical_data_store:
                        historical_context += f"Historical Performance: {json.dumps(historical_data_store[name])}\n"
                    # Add live data (injury, form, fixtures)
                    player_id = next((pid for pid, pdata in live_data['player_details'].items() if pdata['name'] == name), None)
                    if player_id:
                        details = live_data['player_details'][player_id]
                        team_name = live_data['bootstrap']['teams'][details['team_id']-1]['short_name']
                        historical_context += (f"Live Status: Form: {details['form']}, "
                                               f"Injury: {details['news'] if details['news'] else 'Available'}\n")
                        historical_context += f"Upcoming Fixtures for {team_name}: {', '.join(live_data['upcoming_fixtures'].get(team_name, []))}\n"

                historical_context += "---------------------------------\n"
                print(f"Retrieved context for: {', '.join(retrieved_players)}")

        prompt = f"""
        You are "FPL AI", a world-class Fantasy Premier League analyst. Your tone is insightful, data-driven, and slightly witty.
        A user is asking for advice.

        First, consider the user's current team data for Gameweek {team_data.gameweek}:
        {team_data.model_dump_json(indent=2)}

        Second, consider this potentially relevant live and historical context retrieved from your knowledge base:
        {historical_context if historical_context else "No specific context was found to be relevant to the user's question."}

        Finally, answer the user's question: "{request.question}"

        Follow these rules for your response:
        1.  **Formatting is key.** Use Markdown for clarity. Use bold text for player names and key terms. Use bullet points (*) for lists of suggestions.
        2.  **Be Concise.** Get straight to the point. Avoid repetitive phrases.
        3.  **Synthesize.** Combine information from the user's current team, live data (form, injuries, fixtures), and historical context to form your answer.
        4.  **Cite Your Sources.** If you use specific data, mention it (e.g., "**Salah** is in great form (9.0) and has a good upcoming fixture against Luton (H) [2].").
        5.  **Be Honest About Limitations.** If the data is insufficient, state this clearly and provide actionable advice on what the user should look for themselves.
        6.  **Structure your answer.** Start with a direct recommendation, then provide the reasoning and supporting data.
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
