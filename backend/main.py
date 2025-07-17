# backend/main.py

import os
import httpx
import google.generativeai as genai
import asyncio
import json
from pathlib import Path
import numpy as np
import faiss # Vector database library
from sentence_transformers import SentenceTransformer # Embedding model
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
FPL_API_TEAM_PICKS = "https://fantasy.premierleague.com/api/entry/{team_id}/event/{gameweek}/picks/"
DATA_DIR = Path(__file__).parent / "fpl_data"
PROCESSED_DATA_PATH = DATA_DIR / "processed_player_data.json"
FAISS_INDEX_PATH = DATA_DIR / "player_data.index"

# --- In-Memory Stores ---
fpl_bootstrap_cache = TTLCache(maxsize=1, ttl=21600)
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
    
    # 1. Load historical data
    if PROCESSED_DATA_PATH.exists():
        print("Loading historical player data...")
        with open(PROCESSED_DATA_PATH, 'r', encoding='utf-8') as f:
            historical_data_store = json.load(f)
        # Create a map from integer ID to player name
        player_id_map = {i: name for i, name in enumerate(historical_data_store.keys())}
        print("✅ Historical data loaded.")
    else:
        print("⚠️ Historical data file not found.")

    # 2. Load embedding model
    print("Loading sentence transformer model...")
    embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    print("✅ Embedding model loaded.")

    # 3. Load FAISS index
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

# (Pydantic Models and Helper Functions remain the same)
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

async def get_bootstrap_data():
    if 'bootstrap_data' in fpl_bootstrap_cache:
        return fpl_bootstrap_cache['bootstrap_data']
    async with httpx.AsyncClient() as client:
        res = await client.get(FPL_API_BOOTSTRAP)
        res.raise_for_status()
        data = res.json()
        fpl_bootstrap_cache['bootstrap_data'] = data
        return data

async def get_team_data(team_id: int):
    try:
        bootstrap_data = await get_bootstrap_data()
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
                historical_context += "\n\n--- Relevant Historical Context ---\n"
                for name in retrieved_players:
                    historical_context += f"Player: {name}\n"
                    historical_context += json.dumps(historical_data_store[name], indent=2) + "\n"
                historical_context += "---------------------------------\n"
                print(f"Retrieved context for: {', '.join(retrieved_players)}")

        # --- NEW & IMPROVED PROMPT ---
        prompt = f"""
        You are "FPL AI", a world-class Fantasy Premier League analyst. Your tone is insightful, data-driven, and slightly witty.
        A user is asking for advice.

        First, consider the user's current team data for Gameweek {team_data.gameweek}:
        {team_data.model_dump_json(indent=2)}

        Second, consider this potentially relevant historical context retrieved from your knowledge base based on the user's question:
        {historical_context if historical_context else "No specific historical data was found to be relevant to the user's question."}

        Finally, answer the user's question: "{request.question}"

        Follow these rules for your response:
        1.  Synthesize information from BOTH the user's current team and the historical context to form your answer.
        2.  If the historical data helps answer the question, explicitly mention the key stats (e.g., "Last season, Palmer was great value at £5.5m, scoring 244 points.").
        3.  If the provided data is insufficient to give a definitive answer (e.g., for predicting future minutes or form), state this clearly. Then, provide actionable advice on what the user should look for themselves (e.g., "To find a cheap midfielder for GW38, check recent match reports for players getting consistent starts and look at predicted lineups on sites like Fantasy Football Scout.").
        4.  Keep your response concise, helpful, and easy to read.
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
