# backend/chip_service.py

from typing import Dict, List, Any

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
    
    difficulty_score = (avg_difficulty * 0.3) - (len(double_gw_teams) * 5)
    
    return {
        "gameweek": gw,
        "difficulty_score": round(difficulty_score, 2),
        "teams_with_multiple_fixtures": len(double_gw_teams),
        "avg_fixture_difficulty": round(avg_difficulty, 2),
    }

def get_recommended_players(live_data: Dict[str, Any], position_filter: int = None, limit: int = 5) -> List[Dict]:
    """
    Gets player recommendations based on form, fixture difficulty, and total points.
    """
    players = live_data["bootstrap"]["elements"]
    if position_filter:
        players = [p for p in players if p["element_type"] == position_filter]

    position_map = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    teams_map = {team['id']: team for team in live_data["bootstrap"]["teams"]}

    player_scores = []
    for player in players:
        team_id = player["team"]
        form = float(player.get("form", 0))
        points = player.get("total_points", 0)
        minutes = player.get("minutes", 0)
        
        if minutes < 500: # Filter out players with very few minutes
            continue

        team_info = teams_map.get(team_id)
        if not team_info:
            continue
            
        team_short_name = team_info['short_name']
        upcoming_fixtures_text = live_data['upcoming_fixtures'].get(team_short_name, [])
        
        # A simple heuristic for fixture difficulty from the text
        try:
            avg_difficulty = sum([int(f.split('[')[1].split(']')[0]) for f in upcoming_fixtures_text]) / len(upcoming_fixtures_text)
        except (IndexError, ValueError):
            avg_difficulty = 3 # Default difficulty

        # Composite score
        score = (form * 3) + ((5 - avg_difficulty) * 1.5) + (points / 20)
        
        player_scores.append({
            "name": player["web_name"],
            "team": team_info["name"],
            "position": position_map.get(player["element_type"]),
            "price": player["now_cost"] / 10.0,
            "form": form,
            "points": points,
            "score": round(score, 2)
        })

    return sorted(player_scores, key=lambda x: x["score"], reverse=True)[:limit]


async def calculate_chip_recommendations(live_data: Dict[str, Any], number_of_recommendations: int = 3) -> Dict:
    """
    Calculates and recommends optimal gameweeks for using FPL chips.
    """
    try:
        bootstrap_data = live_data["bootstrap"]
        all_fixtures = live_data["all_fixtures"]
        teams_map = {team["id"]: team for team in bootstrap_data["teams"]}
        current_gw = next((gw['id'] for gw in bootstrap_data['events'] if gw['is_current']), 1)

        team_fixtures_by_gw = identify_double_gameweeks(all_fixtures, current_gw)
        
        gameweek_metrics = []
        future_gameweeks = sorted([gw for gw in team_fixtures_by_gw.keys() if gw >= current_gw])
        
        for gw in future_gameweeks:
            if gw in team_fixtures_by_gw:
                metrics = calculate_gameweek_difficulty(gw, team_fixtures_by_gw[gw], all_fixtures, teams_map)
                gameweek_metrics.append(metrics)
            
        bench_boost_recs = sorted(
            gameweek_metrics,
            key=lambda x: (-x["teams_with_multiple_fixtures"], x["avg_fixture_difficulty"])
        )[:number_of_recommendations]
        
        triple_captain_recs = sorted(
            gameweek_metrics,
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
