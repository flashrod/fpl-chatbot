import pandas as pd
import numpy as np

class DraftEngine:
    def __init__(self, all_players_df: pd.DataFrame):
        self.players_df = all_players_df.copy()
        self.players_df['Player'] = self.players_df.index
        self.squad_data = []
        self.budget = 100.0
        self.team_counts = {}
        self.position_counts = {'GKP': 0, 'DEF': 0, 'MID': 0, 'FWD': 0}

    def _calculate_value(self):
        """
        Calculates a more intelligent value score for each player.
        This score gives exponential value to higher ICT players to prioritize elite assets.
        """
        self.players_df['ict_index'] = pd.to_numeric(self.players_df['ict_index'], errors='coerce').fillna(0)
        self.players_df['now_cost'] = pd.to_numeric(self.players_df['now_cost'], errors='coerce').fillna(0)
        
        cost = (self.players_df['now_cost'] / 10.0).replace(0, np.inf)

        self.players_df['value'] = (self.players_df['ict_index']**2) / cost

    def _is_addable(self, player) -> bool:
        """Checks if a player can be added to the squad based on FPL rules."""
        if self.budget < (player.now_cost / 10.0):
            return False
        if self.team_counts.get(player.team_name, 0) >= 3:
            return False
        return True

    def _add_player(self, player):
        """Adds a player's essential info to the squad and updates constraints."""
        essential_data = {
            'Player': player.name,
            'now_cost': player.now_cost,
            'position': player.position,
            'team_name': player.team_name,
            'id': player.id
        }
        self.squad_data.append(essential_data)
        
        self.budget -= (player.now_cost / 10.0)
        self.team_counts[player.team_name] = self.team_counts.get(player.team_name, 0) + 1
        self.position_counts[player.position] = self.position_counts.get(player.position, 0) + 1
        self.players_df.drop(player.name, inplace=True)
        
    def create_draft(self) -> pd.DataFrame:
        """The main method to generate a full 15-man squad."""
        self._calculate_value()
        
        self.players_df.sort_values(by='value', ascending=False, inplace=True)

        position_targets = {'GKP': 2, 'DEF': 5, 'MID': 5, 'FWD': 3}

        for position, count in position_targets.items():
            position_pool = self.players_df[self.players_df['position'] == position]
            
            for index, player in position_pool.iterrows():
                if self.position_counts[position] < count and self._is_addable(player):
                    self._add_player(player)

        return pd.DataFrame(self.squad_data)