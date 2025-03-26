import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from nba_api.stats.endpoints import playergamelog, playercareerstats, playerdashboardbygeneralsplits
from nba_api.stats.static import players

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('analysis.player_stats')


class PlayerStatsCollector:
    """
    Collects and processes historical player statistics using the NBA API.
    Focused on retrieving time-series compatible metrics for ARIMA modeling.
    """
    
    def __init__(self, db=None):
        """
        Initialize the PlayerStatsCollector.
        
        Args:
            db: Database instance (optional, for storing retrieved stats)
        """
        self.db = db
        
    def get_player_id(self, player_name: str) -> Optional[str]:
        """
        Get NBA API player ID from player name.
        
        Args:
            player_name: Player's full name
            
        Returns:
            Player ID as string or None if not found
        """
        try:
            # Search for player by name
            player_dict = players.find_players_by_full_name(player_name)
            
            if player_dict and len(player_dict) > 0:
                return player_dict[0]['id']
            
            # If full name search fails, try last name
            last_name = player_name.split()[-1]
            player_dict = players.find_players_by_last_name(last_name)
            
            if player_dict and len(player_dict) > 0:
                # Find closest match if multiple results
                for player in player_dict:
                    if player_name.lower() in player['full_name'].lower():
                        return player['id']
                
                # If no close match, return first result
                return player_dict[0]['id']
            
            logger.warning(f"Could not find player ID for: {player_name}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting player ID for {player_name}: {str(e)}")
            return None
    
    def get_recent_game_logs(self, player_name: str, num_games: int = 30) -> Optional[pd.DataFrame]:
        """
        Retrieve recent game logs for a player.
        
        Args:
            player_name: Player's full name
            num_games: Number of recent games to retrieve (default 30)
            
        Returns:
            DataFrame with game-by-game stats or None if retrieval fails
        """
        try:
            # Get player ID
            player_id = self.get_player_id(player_name)
            if not player_id:
                return None
            
            # Get current season in format YYYY-YY
            from datetime import datetime
            current_year = datetime.now().year
            current_month = datetime.now().month
            
            # If between January and September, use previous year
            if current_month < 10:
                season = f"{current_year-1}-{str(current_year)[-2:]}"
            else:
                season = f"{current_year}-{str(current_year+1)[-2:]}"
            
            # Get game logs for most recent season
            game_logs = playergamelog.PlayerGameLog(
                player_id=player_id,
                season=season
            )
            df = game_logs.get_data_frames()[0]
            
            # If we don't have enough games from current season, get previous season too
            if len(df) < num_games:
                prev_season = f"{int(season.split('-')[0])-1}-{int(season.split('-')[0])%100:02d}"
                prev_logs = playergamelog.PlayerGameLog(
                    player_id=player_id,
                    season=prev_season
                )
                prev_df = prev_logs.get_data_frames()[0]
                
                # Combine current and previous season
                df = pd.concat([df, prev_df])
            
            # Take only requested number of games
            df = df.head(num_games)
            
            if len(df) == 0:
                logger.warning(f"No game logs found for player: {player_name}")
                return None
                
            return df
            
        except Exception as e:
            logger.error(f"Error retrieving game logs for {player_name}: {str(e)}")
            return None
    
    def calculate_advanced_metrics(self, game_logs: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate advanced metrics from raw game logs.
        
        Args:
            game_logs: DataFrame with raw game log stats
            
        Returns:
            DataFrame with added advanced metrics
        """
        # Make a copy to avoid modifying the original
        df = game_logs.copy()
        
        try:
            # Convert necessary columns to numeric format
            numeric_cols = ['MIN', 'FGM', 'FGA', 'FG3M', 'FG3A', 'FTM', 'FTA', 
                           'OREB', 'DREB', 'REB', 'AST', 'STL', 'BLK', 'TOV', 'PF', 'PTS',
                           'PLUS_MINUS']
            
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                else:
                    logger.warning(f"Column {col} not found in game logs")
            
            # Fill NaN values with 0
            df = df.fillna(0)
            
            # Calculate minutes as float (convert '12:34' format to minutes)
            df['MINUTES_PLAYED'] = df['MIN'].apply(
                lambda x: float(x.split(':')[0]) + float(x.split(':')[1])/60 if isinstance(x, str) and ':' in x else float(x)
            )
            
            # 1. Field Goal Percentage (FG%)
            df['FG_PCT'] = np.where(df['FGA'] > 0, df['FGM'] / df['FGA'], 0)
            
            # 2. True Shooting Percentage (TS%)
            # TS% = PTS / (2 * (FGA + 0.44 * FTA))
            df['TS_PCT'] = np.where(
                (df['FGA'] + 0.44 * df['FTA']) > 0,
                df['PTS'] / (2 * (df['FGA'] + 0.44 * df['FTA'])),
                0
            )
            
            # 3. Points per Minute
            df['PTS_PER_MIN'] = np.where(df['MINUTES_PLAYED'] > 0, df['PTS'] / df['MINUTES_PLAYED'], 0)
            
            # 4. Plus/Minus already in the data as PLUS_MINUS
            
            # 5/6. Offensive & Defensive Ratings (simplified approximations)
            # These are complex ratings that usually require team data
            # Using simplified calculations based on individual performance
            
            # Possessions approximation = FGA - OREB + TOV + 0.44*FTA
            df['POSS'] = df['FGA'] - df['OREB'] + df['TOV'] + 0.44 * df['FTA']
            
            # Offensive Rating = Points produced per 100 possessions
            df['OFF_RATING'] = np.where(df['POSS'] > 0, 100 * (df['PTS'] + 1.5 * df['AST']) / df['POSS'], 0)
            
            # Defensive Rating = Points allowed per 100 possessions (rough approximation)
            # This is a simplified version (truly accurate defensive rating requires team data)
            df['DEF_RATING'] = np.where(
                df['MINUTES_PLAYED'] > 0,
                100 - (5 * (df['STL'] + df['BLK']) - df['PF'] - df['PLUS_MINUS']) / df['MINUTES_PLAYED'],
                0
            )
            
            # 7. Game Score (John Hollinger's formula)
            # GmSc = PTS + 0.4*FGM - 0.7*FGA - 0.4*(FTA-FTM) + 0.7*OREB + 0.3*DREB + STL + 0.7*AST + 0.7*BLK - 0.4*PF - TOV
            df['GAME_SCORE'] = (
                df['PTS'] + 0.4 * df['FGM'] - 0.7 * df['FGA'] - 0.4 * (df['FTA'] - df['FTM']) 
                + 0.7 * df['OREB'] + 0.3 * df['DREB'] + df['STL'] + 0.7 * df['AST'] 
                + 0.7 * df['BLK'] - 0.4 * df['PF'] - df['TOV']
            )
            
            # 8. Usage Rate (simplified version)
            # USG% = 100 * ((FGA + 0.44 * FTA + TOV) * (Team MP / 5)) / (MP * (Team FGA + 0.44 * Team FTA + Team TOV))
            # Since team data isn't in game logs, using approximation:
            df['USG_RATE'] = 100 * (df['FGA'] + 0.44 * df['FTA'] + df['TOV']) / df['POSS']
            
            # 9. Minutes Played already calculated as MINUTES_PLAYED
            
            # 10. Assist-to-Turnover Ratio
            df['AST_TO_RATIO'] = np.where(df['TOV'] > 0, df['AST'] / df['TOV'], df['AST'])
            
            return df
            
        except Exception as e:
            logger.error(f"Error calculating advanced metrics: {str(e)}")
            return game_logs  # Return original if calculation fails
    
    def get_player_stats(self, player_name: str, num_games: int = 30) -> Optional[pd.DataFrame]:
        """
        Retrieve and process player stats for time series analysis.
        
        Args:
            player_name: Player's full name
            num_games: Number of recent games to retrieve
            
        Returns:
            DataFrame with time series compatible stats or None if retrieval fails
        """
        # Log the start of player stats retrieval
        logger.info(f"Retrieving stats for player: {player_name}")
        
        # Get basic game logs
        game_logs = self.get_recent_game_logs(player_name, num_games)
        if game_logs is None:
            logger.warning(f"No game logs found for player: {player_name}")
            return None
        
        # Calculate advanced metrics
        player_stats = self.calculate_advanced_metrics(game_logs)
        
        # Select only the metrics we need for time series analysis
        if player_stats is not None:
            # Define columns to keep for time series analysis
            ts_columns = [
                'GAME_DATE', 'GAME_ID',  # Identifiers
                'FG_PCT', 'TS_PCT', 'PTS_PER_MIN',  # Efficiency metrics
                'PLUS_MINUS', 'OFF_RATING', 'DEF_RATING', 'GAME_SCORE',  # Impact metrics
                'USG_RATE', 'MINUTES_PLAYED', 'AST_TO_RATIO'  # Usage metrics
            ]
            
            # Keep only columns that exist in the dataframe
            available_columns = [col for col in ts_columns if col in player_stats.columns]
            
            # Filter and sort by date (most recent first)
            filtered_stats = player_stats[available_columns].sort_values('GAME_DATE', ascending=False)
            
            logger.info(f"Successfully retrieved stats for player: {player_name}")
            return filtered_stats
        
        return None
    
    def get_team_players_stats(self, team_name: str, lineup: List[Dict[str, Any]]) -> Dict[str, pd.DataFrame]:
        """
        Retrieve stats for all players in a team's lineup.
        
        Args:
            team_name: Name of the team
            lineup: List of player dictionaries
            
        Returns:
            Dictionary mapping player names to their stats DataFrames
        """
        team_stats = {}
        
        for player in lineup:
            player_name = player.get('name')
            if not player_name:
                continue
                
            # Skip injured players (optional)
            status = player.get('status')
            if status and status != 'active':
                logger.info(f"Skipping injured player: {player_name} ({status})")
                continue
                
            # Get player stats
            player_stats = self.get_player_stats(player_name)
            
            if player_stats is not None and not player_stats.empty:
                team_stats[player_name] = player_stats
            
        logger.info(f"Retrieved stats for {len(team_stats)} players from {team_name}")
        return team_stats
    
    def get_game_players_stats(self, game_id: str) -> Dict[str, Dict[str, pd.DataFrame]]:
        """
        Retrieve stats for all players in a game from the database.
        
        Args:
            game_id: Game ID
            
        Returns:
            Dictionary with team names as keys and team player stats as values
        """
        if not self.db:
            logger.error("Database connection not available")
            return {}
            
        game_stats = {}
        
        try:
            # Get game details
            game = self.db.get_game(game_id)
            if not game:
                logger.error(f"Game not found: {game_id}")
                return {}
                
            # Get players for the game
            players = self.db.get_players_for_game(game_id)
            
            # Group players by team
            home_players = [p for p in players if p['team'] == game['home_team']]
            away_players = [p for p in players if p['team'] == game['away_team']]
            
            # Get stats for each team
            game_stats[game['home_team']] = self.get_team_players_stats(game['home_team'], home_players)
            game_stats[game['away_team']] = self.get_team_players_stats(game['away_team'], away_players)
            
            return game_stats
            
        except Exception as e:
            logger.error(f"Error getting game players stats for {game_id}: {str(e)}")
            return {}
    
    def collect_stats_for_todays_games(self) -> int:
        """
        Collect historical stats for all players in today's games.
        
        Returns:
            Number of games processed
        """
        if not self.db:
            logger.error("Database connection not available")
            return 0
            
        processed_count = 0
        
        try:
            # Get today's games from database
            todays_games = self.db.get_todays_games()
            
            for game in todays_games:
                game_id = game['game_id']
                
                # Get player stats for this game
                game_stats = self.get_game_players_stats(game_id)
                
                # Store the stats in the database
                if game_stats:
                    for team_name, team_stats in game_stats.items():
                        for player_name, player_stats in team_stats.items():
                            # Store player stats
                            if self.db.store_player_stats(player_name, player_stats):
                                logger.info(f"Stored historical stats for {player_name}")
                
                processed_count += 1
                logger.info(f"Processed stats for game: {game_id}")
                
            return processed_count
            
        except Exception as e:
            logger.error(f"Error collecting stats for today's games: {str(e)}")
            return processed_count


# Example usage when run as script
if __name__ == "__main__":
    # Create the player stats collector (without DB for testing)
    collector = PlayerStatsCollector()
    
    # Test with a single player
    player_name = "LeBron James"
    stats = collector.get_player_stats(player_name, num_games=10)
    
    if stats is not None:
        print(f"\nStats for {player_name}:")
        print(stats[['GAME_DATE', 'FG_PCT', 'PTS_PER_MIN', 'PLUS_MINUS', 'GAME_SCORE']].head())