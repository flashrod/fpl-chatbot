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

# Import the new chip service
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
PROCESSED_DATA_PATH = DATA_DIR / "processed_player_data.json"
FAISS_INDEX_PATH = DATA_DIR / "player_data.index"

# --- In-Memory Stores ---
fpl_live_data_cache = TTLCache(maxsize=1, ttl=3600)
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
    if 'live_data' in fpl_live_data_cache:
        return fpl_live_data_cache['live_data']
    
    print("CACHE MISS: Fetching new live data from FPL API.")
    async with httpx.AsyncClient() as client:
        bootstrap_task = client.get(FPL_API_BOOTSTRAP)
        fixtures_task = client.get(FPL_API_FIXTURES)
        bootstrap_res, fixtures_res = await asyncio.gather(bootstrap_task, fixtures_task)
        
        bootstrap_data = bootstrap_res.json()
        fixtures_data = fixtures_res.json()

        teams_map = {team['id']: team['short_name'] for team in bootstrap_data['teams']}
        
        player_details = {p['id']: {'name': p['web_name'], 'team_id': p['team'], 'status': p['status'], 'news': p['news'], 'form': p['form']} for p in bootstrap_data['elements']}
        
        upcoming_fixtures = {}
        current_gameweek = next((gw['id'] for gw in bootstrap_data['events'] if gw['is_current']), None)
        if current_gameweek:
            for team_id_num in teams_map:
                team_fixtures = [
                    f"{teams_map.get(f['team_a'])} (A) [{f.get('team_a_difficulty', 3)}]" if f.get('team_h') != team_id_num else f"{teams_map.get(f['team_h'])} (H) [{f.get('team_h_difficulty', 3)}]"
                    for f in fixtures_data 
                    if f.get('event') and f.get('team_h') and f.get('team_a') and (f['team_h'] == team_id_num or f['team_a'] == team_id_num) and f['event'] >= current_gameweek
                ]
                upcoming_fixtures[teams_map[team_id_num]] = team_fixtures[:3]

        live_data = {
            "bootstrap": bootstrap_data,
            "all_fixtures": fixtures_data,
            "player_details": player_details,
            "upcoming_fixtures": upcoming_fixtures
        }
        fpl_live_data_cache['live_data'] = live_data
        return live_data

@app.get("/api/get-team-data/{team_id}", response_model=TeamData)
async def get_team_data(team_id: int):
    """
    Fetches the user's FPL team data. It now handles the pre-season case
    where player picks for GW1 might not be available yet.
    """
    try:
        live_data = await get_live_fpl_data()
        bootstrap_data = live_data['bootstrap']
        
        current_gameweek = next((gw['id'] for gw in bootstrap_data['events'] if gw['is_current']), 1)
        player_map = {p['id']: {'name': p['web_name'], 'cost': p['now_cost'] / 10} for p in bootstrap_data['elements']}
        position_map = {p_type['id']: p_type['singular_name_short'] for p_type in bootstrap_data['element_types']}
        
        team_picks_url = FPL_API_TEAM_PICKS.format(team_id=team_id, gameweek=current_gameweek)
        
        players = []
        async with httpx.AsyncClient() as client:
            # First, check if the team entry exists to validate the ID
            entry_res = await client.get(f"https://fantasy.premierleague.com/api/entry/{team_id}/")
            if entry_res.status_code != 200:
                raise HTTPException(status_code=404, detail=f"FPL Team ID {team_id} not found.")

            # Now, try to get the picks
            picks_res = await client.get(team_picks_url)
            
            # If picks are found (200 OK), process them.
            # If not found (404), just continue with an empty player list, which is fine for pre-season.
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

    except HTTPException as http_exc:
        # Re-raise HTTP exceptions to be handled by FastAPI
        raise http_exc
    except Exception as e:
        # Catch any other unexpected errors
        print(f"Error in get_team_data: {e}")
        raise HTTPException(status_code=500, detail="An unexpected server error occurred.")


# --- API Endpoints ---
@app.get("/api/chip-recommendations")
async def get_chip_recommendations():
    live_data = await get_live_fpl_data()
    return await chip_service.calculate_chip_recommendations(live_data)

@app.get("/api/player-recommendations")
async def get_player_recommendations(position: int = None):
    live_data = await get_live_fpl_data()
    return chip_service.get_recommended_players(live_data, position_filter=position, limit=10)

async def stream_chat_response(request: ChatRequest):
    try:
        team_data = await get_team_data(request.team_id)
        live_data = await get_live_fpl_data()

        context_players = set()
        if vector_index and embedding_model:
            question_embedding = embedding_model.encode([request.question])
            k = 3
            _, indices = vector_index.search(question_embedding, k)
            for i in indices[0]:
                if i != -1:
                    player_name = player_id_map.get(i)
                    if player_name:
                        context_players.add(player_name)
        
        for player in team_data.players:
            context_players.add(player.name)

        context_block = ""
        if context_players:
            context_block += "\n\n--- CONTEXTUAL DATA ---\n"
            for name in sorted(list(context_players)):
                context_block += f"Player: **{name}**\n"
                player_id = next((pid for pid, pdata in live_data['player_details'].items() if pdata['name'] == name), None)
                if player_id:
                    details = live_data['player_details'][player_id]
                    team_id_num = details.get('team_id')
                    if team_id_num:
                        team_name = next((t['short_name'] for t in live_data['bootstrap']['teams'] if t['id'] == team_id_num), None)
                        if team_name:
                            context_block += (f"* **Live Status:** Form: {details.get('form', 'N/A')}, "
                                              f"Injury: {details.get('news', 'Available') or 'Available'}\n")
                            context_block += f"* **Upcoming Fixtures for {team_name}:** {', '.join(live_data['upcoming_fixtures'].get(team_name, ['N/A']))}\n"
                if name in historical_data_store:
                    context_block += f"* **Historical Note:** {json.dumps(historical_data_store[name])}\n"
            context_block += "-----------------------\n"

        prompt = f"""
        You are "FPL AI", a world-class Fantasy Premier League analyst. Your tone is insightful, data-driven, and slightly witty.
        Your task is to answer the user's question based on all the data provided.

        **Reasoning Hierarchy (IMPORTANT):**
        1.  **Prioritize Live Data:** Your primary analysis MUST be based on current form, injury status, and upcoming fixtures. This is the most critical information.
        2.  **Consider User's Team:** Analyze the players the user actually owns.
        3.  **Use Historical Data as Secondary Context:** Only use historical data to support your analysis of current form (e.g., "he has a history of performing well in the final gameweeks") or if the question is specifically about the past. Do NOT base your primary recommendation on historical data.

        **Response Rules:**
        * **Structure:**
            1.  **Assessment:** Start with a one-sentence summary of the situation.
            2.  **Key Insights:** Use a bulleted list (*) to present the most important points from your analysis.
            3.  **Recommendation:** End with a clear, actionable recommendation.
        * **Formatting:** Use Markdown. Use **bold** for player names and key terms.
        * **Conciseness:** Be direct. Do not repeat information or use filler phrases.
        * **Honesty:** If the data is insufficient, state it clearly and suggest where the user can find the information they need (e.g., "For the latest team news, check Fantasy Football Scout.").

        ---
        **User's Question:** "{request.question}"
        
        **User's Team Data:**
        {team_data.model_dump_json(indent=2)}

        **Contextual Data:**
        {context_block if context_block else "No specific context was found to be relevant to the user's question."}
        ---
        
        Now, provide your expert analysis.
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
