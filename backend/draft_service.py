import pandas as pd

class DraftEngine:
    def __init__(self, all_players_df: pd.DataFrame):
        self.players_df = all_players_df.copy()
        # Ensure 'Player' column exists from the index
        self.players_df['Player'] = self.players_df.index
        self.squad = []
        self.budget = 100.0
        self.team_counts = {}
        self.position_counts = {'GKP': 0, 'DEF': 0, 'MID': 0, 'FWD': 0}

    def _calculate_value(self):
        """Calculates a value score for each player."""
        # A simple value score: total points per million pounds.
        # We can make this more complex later (e.g., adding xG, fixtures).
        self.players_df['value'] = self.players_df['total_points'] / (self.players_df['now_cost'] + 1)

    def _is_addable(self, player) -> bool:
        """Checks if a player can be added to the squad based on FPL rules."""
        # Check budget
        if self.budget < (player.now_cost / 10.0):
            return False
        # Check team limit (max 3 players from one team)
        if self.team_counts.get(player.team_name, 0) >= 3:
            return False
        return True

    def _add_player(self, player):
        """Adds a player to the squad and updates constraints."""
        self.squad.append(player)
        self.budget -= (player.now_cost / 10.0)
        self.team_counts[player.team_name] = self.team_counts.get(player.team_name, 0) + 1
        self.position_counts[player.position] = self.position_counts.get(player.position, 0) + 1
        # Remove the player from the pool of available players
        self.players_df.drop(player.name, inplace=True)
        
    def create_draft(self) -> pd.DataFrame:
        """The main method to generate a full 15-man squad."""
        self._calculate_value()
        
        # Sort all players by their value score, descending
        self.players_df.sort_values(by='value', ascending=False, inplace=True)

        position_targets = {'GKP': 2, 'DEF': 5, 'MID': 5, 'FWD': 3}

        for position, count in position_targets.items():
            position_pool = self.players_df[self.players_df['position'] == position]
            
            for index, player in position_pool.iterrows():
                if self.position_counts[position] < count and self._is_addable(player):
                    self._add_player(player)

        return pd.DataFrame(self.squad)