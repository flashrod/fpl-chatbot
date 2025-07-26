# backend/live_data_service.py
import httpx
import asyncio
from typing import List, Dict

# --- Pydantic Models for Live Data ---
# These can be moved to a central models.py file later if needed
from pydantic import BaseModel

class LivePlayerStats(BaseModel):
    minutes: int
    goals_scored: int
    assists: int
    clean_sheets: int
    saves: int
    bonus: int
    total_points: int

class LivePlayer(BaseModel):
    id: int
    name: str
    team_name: str
    stats: LivePlayerStats
    is_captain: bool = False
    is_vice_captain: bool = False
    effective_ownership: float = 0.0
    live_points: int = 0

class LiveGameweekData(BaseModel):
    team_id: int
    gameweek: int
    total_points: int
    players: List[LivePlayer]
    active_chip: str | None = None

# --- API URLs ---
FPL_API_LIVE_GAMEWEEK = "https://fantasy.premierleague.com/api/event/{gameweek}/live/"
FPL_API_TEAM_PICKS = "https://fantasy.premierleague.com/api/entry/{team_id}/event/{gameweek}/picks/"

async def get_live_gameweek_data(team_id: int, gameweek: int, master_fpl_data):
    """
    Fetches and calculates live gameweek data for a specific user team.
    """
    if master_fpl_data is None:
        raise ValueError("Master FPL data is not loaded.")
    
    live_url = FPL_API_LIVE_GAMEWEEK.format(gameweek=gameweek)
    picks_url = FPL_API_TEAM_PICKS.format(team_id=team_id, gameweek=gameweek)

    async with httpx.AsyncClient() as client:
        live_task = client.get(live_url)
        picks_task = client.get(picks_url)
        live_res, picks_res = await asyncio.gather(live_task, picks_task)

    if live_res.status_code != 200:
        raise ConnectionError(f"Live data not available for Gameweek {gameweek}.")
    if picks_res.status_code != 200:
        raise ConnectionError(f"Could not fetch team picks for Team ID {team_id}.")

    live_data = live_res.json()
    picks_data = picks_res.json()

    live_elements = {element['id']: element for element in live_data['elements']}
    
    live_players = []
    total_points = 0

    # --- Handle Auto-subs (Simplified Logic) ---
    # First, separate starting players from bench players
    starting_lineup_ids = [p['element'] for p in picks_data.get('picks', []) if p['position'] <= 11]
    bench_lineup = [p for p in picks_data.get('picks', []) if p['position'] > 11]
    
    # Identify players in the starting lineup who did not play
    starters_who_did_not_play = []
    for player_id in starting_lineup_ids:
        if live_elements.get(player_id, {}).get('stats', {}).get('minutes', 0) == 0:
            starters_who_did_not_play.append(player_id)
            
    # Attempt to substitute them with players from the bench
    subs_made = 0
    for bench_player_pick in sorted(bench_lineup, key=lambda p: p['position']): # Process bench in order
        if not starters_who_did_not_play or subs_made >= len(starters_who_did_not_play):
            break
        
        bench_player_id = bench_player_pick['element']
        if live_elements.get(bench_player_id, {}).get('stats', {}).get('minutes', 0) > 0:
            # A valid substitution can be made
            starting_lineup_ids.remove(starters_who_did_not_play[subs_made])
            starting_lineup_ids.append(bench_player_id)
            subs_made += 1

    # Now, process the final lineup including subs
    for pick in picks_data.get('picks', []):
        player_id = pick['element']
        
        # Skip players not in the final lineup (benched and didn't come on)
        if player_id not in starting_lineup_ids:
            continue

        live_player_stats = live_elements.get(player_id)
        if not live_player_stats:
            continue

        player_info = master_fpl_data[master_fpl_data['id'] == player_id].iloc[0]

        # Simplified Effective Ownership (EO)
        ownership_percentage = player_info.get('selected_by_percent', 0)
        captain_multiplier = 2 if pick.get('is_captain') else 1
        effective_ownership = (ownership_percentage * captain_multiplier)

        # Apply multiplier for captain/vice-captain
        points = live_player_stats['stats']['total_points'] * pick.get('multiplier', 1)
        total_points += points

        live_players.append(LivePlayer(
            id=player_id,
            name=player_info.name,
            team_name=player_info.team_name,
            stats=LivePlayerStats(**live_player_stats['stats']),
            is_captain=pick.get('is_captain', False),
            is_vice_captain=pick.get('is_vice_captain', False),
            effective_ownership=round(effective_ownership, 2),
            live_points=points
        ))
    
    return LiveGameweekData(
        team_id=team_id,
        gameweek=gameweek,
        total_points=total_points,
        players=live_players,
        active_chip=picks_data.get('active_chip')
    )
