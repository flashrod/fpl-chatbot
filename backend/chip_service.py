# backend/chip_service.py
import pandas as pd

def get_all_team_fixture_difficulty(master_fpl_data):
    """
    Reads team fixture data directly from the pre-processed master DataFrame,
    formats it, and returns a sorted list by average difficulty.
    
    Args:
        master_fpl_data: The main DataFrame containing all processed FPL data.
    """
    if master_fpl_data is None:
        return []

    team_data = master_fpl_data[['team_name', 'avg_fixture_difficulty', 'fixture_details']].copy()
    team_data.dropna(subset=['team_name'], inplace=True)
    team_data.drop_duplicates(subset=['team_name'], inplace=True)

    difficulty_list = team_data.to_dict(orient='records')

    formatted_list = [
        {
            "name": item['team_name'],
            "avg_difficulty": item['avg_fixture_difficulty'],
            "fixture_details": item['fixture_details']
        }
        for item in difficulty_list
    ]
    
    return sorted(formatted_list, key=lambda x: x['avg_difficulty'])


def calculate_chip_recommendations(master_fpl_data):
    """
    Analyzes fixture data to recommend opportune moments for using Bench Boost and Triple Captain chips.

    Args:
        master_fpl_data: The main DataFrame containing all processed FPL data.
    """
    if master_fpl_data is None or 'fixture_details' not in master_fpl_data.columns:
        return {"bench_boost": [], "triple_captain": [], "status": "Data not available."}

    # --- Analyze for Double Gameweeks (for Bench Boost) ---
    gameweek_counts = {}
    for index, row in master_fpl_data.iterrows():
        team_name = row.get('team_name')
        if not team_name or not isinstance(row['fixture_details'], list):
            continue
        
        for fixture in row['fixture_details']:
            gw = fixture['gameweek']
            if gw not in gameweek_counts:
                gameweek_counts[gw] = {}
            
            gameweek_counts[gw][team_name] = gameweek_counts[gw].get(team_name, 0) + 1

    bench_boost_recommendations = []
    for gw, teams in gameweek_counts.items():
        double_gw_teams = [team for team, count in teams.items() if count > 1]
        if len(double_gw_teams) >= 2: # Recommend if at least 2 teams have a double gameweek
            bench_boost_recommendations.append({
                "gameweek": gw,
                "teams_with_multiple_fixtures": ", ".join(double_gw_teams),
                "avg_fixture_difficulty": "N/A" # This would require more complex calculation
            })

    # --- Analyze for Triple Captain ---
    # Find players with high form and a very easy single fixture
    triple_captain_recommendations = []
    # Sort players by form to find top candidates
    top_form_players = master_fpl_data.sort_values(by='form', ascending=False).head(20)

    for index, player in top_form_players.iterrows():
        if not isinstance(player['fixture_details'], list) or not player['fixture_details']:
            continue
        
        # Look at the very next fixture
        next_fixture = player['fixture_details'][0]
        
        # A good TC candidate has great form and a fixture difficulty of 2 or less
        if float(player.get('form', 0)) > 7.0 and next_fixture['difficulty'] <= 2:
             triple_captain_recommendations.append({
                "gameweek": next_fixture['gameweek'],
                "player_recommendation": f"{player.name} ({player.team_name}) vs {next_fixture['opponent']}",
                "reason": f"High form ({player.form}) and an easy fixture (Difficulty: {next_fixture['difficulty']})."
            })
             # Limit to a few top recommendations
             if len(triple_captain_recommendations) >= 3:
                 break

    return {
        "bench_boost": sorted(bench_boost_recommendations, key=lambda x: x['gameweek']),
        "triple_captain": triple_captain_recommendations,
        "status": "success"
    }
