# backend/main.py

import os
import httpx
import google.generativeai as genai
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# --- Configuration ---
# Load environment variables from the .env file
load_dotenv()

# Configure the Gemini API with your key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found. Please set it in your .env file.")
genai.configure(api_key=GEMINI_API_KEY)

# --- FPL API URLs ---
FPL_API_BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_API_TEAM_PICKS = "https://fantasy.premierleague.com/api/entry/{team_id}/event/{gameweek}/picks/"

# --- FastAPI App Initialization ---
app = FastAPI(
    title="FPL AI Chatbot API",
    description="API for fetching FPL data and interacting with an AI chatbot.",
    version="1.0.0"
)

# Configure CORS (Cross-Origin Resource Sharing)
# This allows your React frontend (running on a different port) to talk to this backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins, you can restrict this to your frontend's URL in production
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)

# --- Pydantic Models (for data validation) ---
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

# --- API Endpoints ---

@app.get("/")
def read_root():
    """A simple endpoint to check if the API is running."""
    return {"message": "Welcome to the FPL AI Chatbot API"}

@app.get("/api/get-team-data/{team_id}", response_model=TeamData)
async def get_team_data(team_id: int):
    """
    Fetches the user's FPL team data for the current gameweek.
    """
    try:
        async with httpx.AsyncClient() as client:
            # 1. Get general bootstrap data to find the current gameweek and player details
            bootstrap_res = await client.get(FPL_API_BOOTSTRAP)
            bootstrap_res.raise_for_status()
            bootstrap_data = bootstrap_res.json()

            # Find the current gameweek
            current_gameweek = 0
            for gw_info in bootstrap_data['events']:
                if gw_info['is_current']:
                    current_gameweek = gw_info['id']
                    break
            
            if current_gameweek == 0:
                # If no current gameweek (e.g., pre-season), default to gameweek 1
                current_gameweek = 1

            # Create a map of player IDs to their details for easy lookup
            player_map = {p['id']: {'name': p['web_name'], 'cost': p['now_cost'] / 10} for p in bootstrap_data['elements']}
            position_map = {p_type['id']: p_type['singular_name_short'] for p_type in bootstrap_data['element_types']}

            # 2. Get the user's specific team picks for that gameweek
            team_picks_url = FPL_API_TEAM_PICKS.format(team_id=team_id, gameweek=current_gameweek)
            picks_res = await client.get(team_picks_url)
            
            # If the gameweek hasn't started, the picks might not be available.
            # We'll return an empty list in that case.
            if picks_res.status_code == 404:
                 return TeamData(team_id=team_id, gameweek=current_gameweek, players=[])

            picks_res.raise_for_status()
            picks_data = picks_res.json()

            # 3. Combine the data to build the player list
            players = []
            for pick in picks_data['picks']:
                player_id = pick['element']
                player_details = player_map.get(player_id)
                
                # Find player position from bootstrap data
                player_type_id = next((p['element_type'] for p in bootstrap_data['elements'] if p['id'] == player_id), None)
                position = position_map.get(player_type_id, 'N/A')

                if player_details:
                    players.append(Player(
                        name=player_details['name'],
                        position=position,
                        cost=player_details['cost']
                    ))
            
            return TeamData(team_id=team_id, gameweek=current_gameweek, players=players)

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=404, detail=f"Could not find FPL data for Team ID {team_id}. Please check the ID.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


@app.post("/api/chat")
async def chat_with_bot(request: ChatRequest):
    """
    Handles the chat request by sending a formatted prompt to the Gemini AI.
    """
    try:
        # Fetch the latest team data to give the AI context
        team_data = await get_team_data(request.team_id)

        # Create the prompt for the AI
        prompt = f"""
        You are an expert Fantasy Premier League (FPL) assistant.
        A user is asking for advice about their team.

        Here is the user's current team data for Gameweek {team_data.gameweek}:
        {team_data.json(indent=2)}

        Here is the user's question: "{request.question}"

        Please provide a helpful, friendly, and concise response.
        Analyze the team in the context of their question.
        Keep your answer to a few sentences.
        """

        # Call the Gemini API
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = await model.generate_content_async(prompt)

        return {"reply": response.text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get response from AI: {str(e)}")

# --- To run the backend, use the following command in your terminal: ---
# uvicorn main:app --reload
