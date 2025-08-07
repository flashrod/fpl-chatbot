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
        """Calculates an intelligent value score for each player."""
        self.players_df['ict_index'] = pd.to_numeric(self.players_df['ict_index'], errors='coerce').fillna(0)
        self.players_df['now_cost'] = pd.to_numeric(self.players_df['now_cost'], errors='coerce').fillna(0)
        cost = (self.players_df['now_cost'] / 10.0).replace(0, np.inf)
        self.players_df['value'] = (self.players_df['ict_index']**2) / cost
        self.players_df.sort_values(by='value', ascending=False, inplace=True)

    def _is_addable(self, player) -> bool:
        """Checks if a player can be added to the squad based on FPL rules."""
        if self.budget < (player.now_cost / 10.0): return False
        if self.team_counts.get(player.team_name, 0) >= 3: return False
        return True

    def _add_player(self, player):
        """Adds a player's essential info to the squad and updates constraints."""
        essential_data = {
            'Player': player.name, 'now_cost': player.now_cost,
            'position': player.position, 'team_name': player.team_name, 'id': player.id
        }
        self.squad_data.append(essential_data)
        self.budget -= (player.now_cost / 10.0)
        self.team_counts[player.team_name] = self.team_counts.get(player.team_name, 0) + 1
        self.position_counts[player.position] = self.position_counts.get(player.position, 0) + 1
        self.players_df.drop(player.name, inplace=True)

    def _fill_remaining_slots(self, position_targets):
        """A generic greedy filler for remaining slots."""
        for position, count in position_targets.items():
            needed = count - self.position_counts[position]
            if needed <= 0: continue
            
            position_pool = self.players_df[self.players_df['position'] == position]
            for index, player in position_pool.iterrows():
                if self.position_counts[position] < count and self._is_addable(player):
                    self._add_player(player)

    def _draft_balanced(self):
        """Generates a draft using pre-allocated positional budgets."""
        positional_budgets = {'GKP': 8.5, 'DEF': 25.0, 'MID': 35.0, 'FWD': 31.5}
        position_targets = {'GKP': 2, 'DEF': 5, 'MID': 5, 'FWD': 3}

        for position, budget in positional_budgets.items():
            current_pos_budget = budget
            position_pool = self.players_df[self.players_df['position'] == position]
            for index, player in position_pool.iterrows():
                player_cost = player.now_cost / 10.0
                if self.position_counts[position] < position_targets[position] and self._is_addable(player) and current_pos_budget >= player_cost:
                    self._add_player(player)
                    current_pos_budget -= player_cost
        return pd.DataFrame(self.squad_data)

    def _draft_stars_and_scrubs(self):
        """Generates a draft by picking premium players first, then filling."""
        position_targets = {'GKP': 2, 'DEF': 5, 'MID': 5, 'FWD': 3}

        # Pick 1 premium Midfielder (over 9.0m)
        premium_mids = self.players_df[(self.players_df['position'] == 'MID') & (self.players_df['now_cost'] >= 90)]
        if not premium_mids.empty and self._is_addable(premium_mids.iloc[0]):
            self._add_player(premium_mids.iloc[0])

        # Pick 1 premium Forward (over 9.0m)
        premium_fwds = self.players_df[(self.players_df['position'] == 'FWD') & (self.players_df['now_cost'] >= 90)]
        if not premium_fwds.empty and self._is_addable(premium_fwds.iloc[0]):
            self._add_player(premium_fwds.iloc[0])
        
        # Fill the rest of the squad greedily
        self._fill_remaining_slots(position_targets)
        return pd.DataFrame(self.squad_data)

    def create_draft(self, strategy: str = 'balanced') -> pd.DataFrame:
        """The main method to generate a full 15-man squad based on a strategy."""
        self._calculate_value()
        
        if strategy == 'stars_and_scrubs':
            return self._draft_stars_and_scrubs()
        else: # Default to balanced
            return self._draft_balanced()