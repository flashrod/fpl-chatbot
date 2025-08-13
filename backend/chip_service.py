import pandas as pd
import logging
from pprint import pprint

# --- Set up basic logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --------------------------------------------------------------------------
# ## Feature 1: Simple Fixture Difficulty (Original)
# --------------------------------------------------------------------------

def get_fixture_difficulty_for_next_n_gameweeks(master_fpl_data: pd.DataFrame, current_gameweek: int, n: int = 5) -> list:
    """
    Calculates and ranks team fixture difficulty based only on the next 'n' upcoming gameweeks.
    This is the simple version that does NOT consider the team's own strength.
    """
    if master_fpl_data is None:
        logging.error("Master FPL data is not available for fixture difficulty calculation.")
        return []

    teams_df = master_fpl_data[['team_name', 'fixture_details']].drop_duplicates(subset=['team_name']).dropna()
    ranked_teams = []

    for _, row in teams_df.iterrows():
        team_name = row['team_name']
        all_fixtures = row['fixture_details']
        if not isinstance(all_fixtures, list):
            continue

        upcoming_fixtures = [fix for fix in all_fixtures if fix.get('gameweek', 0) >= current_gameweek][:n]
        if not upcoming_fixtures:
            continue

        avg_difficulty = sum(fix.get('difficulty', 5) for fix in upcoming_fixtures) / len(upcoming_fixtures)
        ranked_teams.append({
            "name": team_name,
            "avg_difficulty": round(avg_difficulty, 2),
            "fixture_details": upcoming_fixtures
        })

    return sorted(ranked_teams, key=lambda x: x.get('avg_difficulty', 99))

# --------------------------------------------------------------------------
# ## Feature 2: Strength-Adjusted Fixture Difficulty (Advanced)
# --------------------------------------------------------------------------

def get_adjusted_fixture_difficulty(master_fpl_data: pd.DataFrame, teams_data: list, current_gameweek: int, n: int = 5) -> list:
    """
    Calculates a "strength-adjusted" fixture difficulty.
    This considers the team's own strength, making easy fixtures even more appealing for strong teams.
    """
    if master_fpl_data is None:
        logging.error("Master FPL data is not available.")
        return []

    team_strength_map = {team['short_name']: team for team in teams_data}
    all_strengths = [team['strength_overall_away'] for team in teams_data] + [team['strength_overall_home'] for team in teams_data]
    if not all_strengths:
        logging.error("No team strength data available.")
        return []
    min_strength, max_strength = min(all_strengths), max(all_strengths)
    
    teams_df = master_fpl_data[['team_name', 'fixture_details']].drop_duplicates(subset=['team_name']).dropna()
    ranked_teams = []

    for _, row in teams_df.iterrows():
        team_name = row['team_name']
        team_stats = team_strength_map.get(team_name)
        if not team_stats:
            continue

        upcoming_fixtures = [fix for fix in row['fixture_details'] if fix.get('gameweek', 0) >= current_gameweek][:n]
        if not upcoming_fixtures:
            continue

        adjusted_difficulties = []
        for fix in upcoming_fixtures:
            base_difficulty = fix.get('difficulty', 5)
            team_strength = team_stats['strength_overall_home'] if fix.get('is_home') else team_stats['strength_overall_away']
            
            # Scale strength to a modifier (e.g., from -0.5 to +0.5)
            if (max_strength - min_strength) == 0:
                strength_modifier = 0
            else:
                normalized_strength = (team_strength - min_strength) / (max_strength - min_strength)
                strength_modifier = (normalized_strength - 0.5)
            
            adjusted_score = base_difficulty - strength_modifier
            adjusted_difficulties.append(adjusted_score)

        avg_adjusted_difficulty = sum(adjusted_difficulties) / len(adjusted_difficulties)
        
        ranked_teams.append({
            "name": team_name,
            "avg_difficulty": round(avg_adjusted_difficulty, 2),
            "fixture_details": upcoming_fixtures
        })

    return sorted(ranked_teams, key=lambda x: x.get('avg_difficulty', 99))

# --------------------------------------------------------------------------
# ## Feature 3: Chip Recommendations (Corrected)
# --------------------------------------------------------------------------

def calculate_chip_recommendations_new(master_fpl_data: pd.DataFrame, current_gameweek: int) -> dict:
    """
    Analyzes fixture data to recommend opportune moments for using chips,
    aligned with the new rules of two chips per season (split at GW19).
    """
    if master_fpl_data is None or 'fixture_details' not in master_fpl_data.columns:
        return {"status": "Data not available."}

    recommendations = {
        "first_half": {"gameweek_range": "GW1-GW19", "bench_boost": [], "triple_captain": []},
        "second_half": {"gameweek_range": "GW20-GW38", "bench_boost": [], "triple_captain": []},
        "wildcard_and_free_hit_notes": {
            "first_half_deadline": "GW19", "second_half_available": "GW20",
            "notes": "Wildcard recommendations are team-dependent. Use the Free Hit for Blank Gameweeks."
        },
        "status": "success"
    }
    
    gameweek_counts = {}
    team_fixtures_df = master_fpl_data[['team_name', 'fixture_details']].drop_duplicates('team_name')

    for _, team_row in team_fixtures_df.iterrows():
        team_name = team_row['team_name']
        fixtures = team_row['fixture_details']
        if not team_name or not isinstance(fixtures, list):
            continue
        
        for fixture in fixtures:
            gw = fixture.get('gameweek')
            if gw:
                if gw not in gameweek_counts:
                    gameweek_counts[gw] = {}
                gameweek_counts[gw][team_name] = gameweek_counts[gw].get(team_name, 0) + 1

    dgw_teams_by_gw = {gw: [team for team, count in teams.items() if count > 1] for gw, teams in gameweek_counts.items()}

    for gw, teams in dgw_teams_by_gw.items():
        if len(teams) >= 4:
            recommendation = {"gameweek": gw, "reason": f"A large Double Gameweek featuring: {', '.join(teams)}."}
            if gw <= 19:
                recommendations["first_half"]["bench_boost"].append(recommendation)
            else:
                recommendations["second_half"]["bench_boost"].append(recommendation)

    top_players = master_fpl_data.sort_values(by='total_points', ascending=False).head(30)
    tc_recs_1, tc_recs_2 = [], []

    for player_name, player in top_players.iterrows():
        team_name, fixtures = player.get('team_name'), player.get('fixture_details')
        if not all([team_name, isinstance(fixtures, list)]):
            continue

        player_dgw = next((gw for gw, teams in dgw_teams_by_gw.items() if team_name in teams and gw >= current_gameweek), None)
        
        if player_dgw:
            dgw_fixtures = [f for f in fixtures if f.get('gameweek') == player_dgw]
            opponents = " & ".join([f.get('opponent') for f in dgw_fixtures])
            rec = {"gameweek": player_dgw, "player_recommendation": f"{player_name} ({team_name}) vs {opponents}", "reason": "Player has a Double Gameweek."}
            if player_dgw <= 19 and len(tc_recs_1) < 3: tc_recs_1.append(rec)
            elif player_dgw > 19 and len(tc_recs_2) < 3: tc_recs_2.append(rec)
        else:
            for fixture in fixtures:
                gw = fixture.get('gameweek')
                if gw >= current_gameweek and fixture.get('difficulty', 5) <= 2:
                    rec = {"gameweek": gw, "player_recommendation": f"{player_name} ({team_name}) vs {fixture.get('opponent')}", "reason": f"Favorable fixture (Difficulty: {fixture.get('difficulty')})."}
                    if gw <= 19 and len(tc_recs_1) < 3: tc_recs_1.append(rec)
                    elif gw > 19 and len(tc_recs_2) < 3: tc_recs_2.append(rec)
                    break 

    recommendations["first_half"]["triple_captain"] = sorted(tc_recs_1, key=lambda x: x['gameweek'])
    recommendations["second_half"]["triple_captain"] = sorted(tc_recs_2, key=lambda x: x['gameweek'])
    
    return recommendations

# --------------------------------------------------------------------------
# ## Example Usage Block for Testing
# --------------------------------------------------------------------------
if __name__ == '__main__':
    mock_player_data = {
        'player_name': ['Salah', 'Saka', 'Gordon', 'Adebayo'],
        'team_name': ['LIV', 'ARS', 'NEW', 'LUT'],
        'total_points': [240, 220, 210, 150],
        'fixture_details': [
            [{'gameweek': 4, 'opponent': 'MUN', 'difficulty': 4, 'is_home': True}, {'gameweek': 5, 'opponent': 'EVE', 'difficulty': 2, 'is_home': False}], 
            [{'gameweek': 4, 'opponent': 'BOU', 'difficulty': 2, 'is_home': False}, {'gameweek': 5, 'opponent': 'WHU', 'difficulty': 3, 'is_home': True}], 
            [{'gameweek': 4, 'opponent': 'AVL', 'difficulty': 4, 'is_home': False}, {'gameweek': 5, 'opponent': 'NFO', 'difficulty': 2, 'is_home': True}], 
            [{'gameweek': 4, 'opponent': 'TOT', 'difficulty': 5, 'is_home': True}, {'gameweek': 5, 'opponent': 'WOL', 'difficulty': 2, 'is_home': False}], 
        ]
    }
    master_df = pd.DataFrame(mock_player_data).set_index('player_name')

    mock_teams_data = [
        {'short_name': 'LIV', 'strength_overall_home': 1300, 'strength_overall_away': 1350},
        {'short_name': 'ARS', 'strength_overall_home': 1280, 'strength_overall_away': 1300},
        {'short_name': 'NEW', 'strength_overall_home': 1150, 'strength_overall_away': 1180},
        {'short_name': 'LUT', 'strength_overall_home': 950, 'strength_overall_away': 1000},
    ]

    current_gameweek = 1

    print("="*50)
    print("\n--- 1. Simple Fixture Difficulty ---\n")
    simple_ranking = get_fixture_difficulty_for_next_n_gameweeks(master_df, current_gameweek)
    pprint(simple_ranking)

    print("\n--- 2. Strength-Adjusted Fixture Difficulty ---\n")
    adjusted_ranking = get_adjusted_fixture_difficulty(master_df, mock_teams_data, current_gameweek)
    pprint(adjusted_ranking)

    print("\n--- 3. Chip Recommendations ---\n")
    chip_advice = calculate_chip_recommendations_new(master_df, current_gameweek)
    pprint(chip_advice)