# backend/chip_service.py

import asyncio
from typing import Dict, List, Any

# We will use the get_live_fpl_data from our main app to ensure we use the same cache
# This avoids making duplicate API calls.

def identify_double_gameweeks(fixtures: List[Dict], current_gw: int) -> Dict[int, Dict[int, int]]:
    """
    Identifies gameweeks where teams play multiple times.
    """
    team_fixtures_by_gw = {}
    future_fixtures = [f for f in fixtures if f.get("event") is not None and f["event"] >= current_gw]
    
    for f in future_fixtures:
        gw = f["event"]
        if gw not in team_fixtures_by_gw:
            team_fixtures_by_gw[gw] = {}
        
        home_team, away_team = f["team_h"], f["team_a"]
        team_fixtures_by_gw[gw][home_team] = team_fixtures_by_gw[gw].get(home_team, 0) + 1
        team_fixtures_by_gw[gw][away_team] = team_fixtures_by_gw[gw].get(away_team, 0) + 1
        
    return team_fixtures_by_gw

def calculate_gameweek_difficulty(gw: int, team_fixtures_in_gw: Dict[int, int], all_fixtures: List[Dict], teams_map: Dict[int, Any]) -> Dict:
    """
    Calculates the difficulty of a single gameweek for chip usage.
    """
    gw_fixtures = [f for f in all_fixtures if f.get("event") == gw]
    
    team_difficulties = {}
    for fixture in gw_fixtures:
        home_team, away_team = fixture["team_h"], fixture["team_a"]
        
        if away_team not in team_difficulties: team_difficulties[away_team] = []
        team_difficulties[away_team].append(fixture["team_h_difficulty"])
        
        if home_team not in team_difficulties: team_difficulties[home_team] = []
        team_difficulties[home_team].append(fixture["team_a_difficulty"])

    team_avg_difficulty = {tid: sum(d) / len(d) for tid, d in team_difficulties.items()}
    
    double_gw_teams = {tid: count for tid, count in team_fixtures_in_gw.items() if count > 1}
    avg_difficulty = sum(team_avg_difficulty.values()) / len(team_avg_difficulty) if team_avg_difficulty else 3
    
    # Lower score is better for chips
    difficulty_score = (avg_difficulty * 0.3) - (len(double_gw_teams) * 0.7 * 10)
    
    return {
        "gameweek": gw,
        "difficulty_score": difficulty_score,
        "teams_with_multiple_fixtures": len(double_gw_teams),
        "avg_fixture_difficulty": avg_difficulty,
        "team_data": {
            team_id: {
                "name": teams_map[team_id]["name"],
                "short_name": teams_map[team_id]["short_name"],
                "fixtures_count": count,
                "avg_difficulty": team_avg_difficulty.get(team_id, 3),
                "fixture_details": [
                    {
                        "opponent": teams_map[f["team_a"]]["short_name"] if f["team_h"] == team_id else teams_map[f["team_h"]]["short_name"],
                        "is_home": f["team_h"] == team_id,
                        "difficulty": f["team_a_difficulty"] if f["team_h"] == team_id else f["team_h_difficulty"]
                    }
                    for f in gw_fixtures if f["team_h"] == team_id or f["team_a"] == team_id
                ]
            }
            for team_id, count in team_fixtures_in_gw.items()
        }
    }

async def calculate_chip_recommendations(live_data: Dict[str, Any], number_of_recommendations: int = 3) -> Dict:
    """
    Calculates and recommends optimal gameweeks for using FPL chips.
    """
    try:
        bootstrap_data = live_data["bootstrap"]
        all_fixtures = live_data["all_fixtures"] # Assuming we add this to live_data
        teams_map = {team["id"]: team for team in bootstrap_data["teams"]}
        current_gw = next((gw['id'] for gw in bootstrap_data['events'] if gw['is_current']), 1)

        team_fixtures_by_gw = identify_double_gameweeks(all_fixtures, current_gw)
        
        gameweek_metrics = {}
        future_gameweeks = sorted([gw for gw in team_fixtures_by_gw.keys() if gw >= current_gw])
        
        for gw in future_gameweeks:
            gameweek_metrics[gw] = calculate_gameweek_difficulty(gw, team_fixtures_by_gw[gw], all_fixtures, teams_map)
            
        # Bench Boost recommendations (more DGWs is better)
        bench_boost_recs = sorted(
            gameweek_metrics.values(),
            key=lambda x: (-x["teams_with_multiple_fixtures"], x["avg_fixture_difficulty"])
        )[:number_of_recommendations]
        
        # Triple Captain recommendations (good fixtures for top teams)
        triple_captain_recs = sorted(
            gameweek_metrics.values(),
            key=lambda x: x["difficulty_score"]
        )[:number_of_recommendations]

        return {
            "bench_boost": bench_boost_recs,
            "triple_captain": triple_captain_recs,
            "status": "success"
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}
