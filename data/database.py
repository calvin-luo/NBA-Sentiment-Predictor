import os
import sqlite3
import datetime
from typing import Dict, List, Tuple, Optional, Any, Union
import logging
from contextlib import contextmanager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('database')

class Database:
    """
    SQLite database manager for the NBA Sentiment Predictor project.
    Handles database connections, schema creation, and CRUD operations.
    """
    
    def __init__(self, db_path: str = "nba_sentiment.db"):
        """
        Initialize the database manager.
        
        Args:
            db_path: Path to the SQLite database file
        """
        # Ensure the data directory exists
        db_dir = os.path.dirname(os.path.abspath(db_path))
        os.makedirs(db_dir, exist_ok=True)
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        
    @contextmanager
    def get_connection(self):
        """
        Context manager for database connections.
        Ensures connections are properly closed even if exceptions occur.
        
        Yields:
            sqlite3.Connection: Database connection
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            # Enable foreign key constraints
            conn.execute("PRAGMA foreign_keys = ON")
            # Return rows as dictionaries
            conn.row_factory = sqlite3.Row
            yield conn
        except sqlite3.Error as e:
            logger.error(f"Database connection error: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()
    
    def connect(self) -> None:
        """Establish a connection to the SQLite database."""
        try:
            self.conn = sqlite3.connect(self.db_path)
            # Enable foreign key constraints
            self.conn.execute("PRAGMA foreign_keys = ON")
            # Return rows as dictionaries
            self.conn.row_factory = sqlite3.Row
            self.cursor = self.conn.cursor()
            logger.info(f"Connected to database: {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Database connection error: {e}")
            raise
    
    def disconnect(self) -> None:
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
            self.cursor = None
            logger.info("Disconnected from database")
    
    def initialize_database(self) -> None:
        """Create all tables if they don't exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create Games table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS games (
                game_id TEXT PRIMARY KEY,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                game_date TEXT NOT NULL,
                game_time TEXT NOT NULL,
                venue TEXT,
                prediction REAL,
                actual_result TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            ''')
            
            # Create Players table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS players (
                player_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                team TEXT NOT NULL,
                status TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(name, team)
            )
            ''')
            
            # Create Reddit Posts table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS reddit_posts (
                post_id INTEGER PRIMARY KEY AUTOINCREMENT,
                reddit_id TEXT UNIQUE NOT NULL,
                subreddit TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT,
                author TEXT,
                created_utc REAL NOT NULL,
                score INTEGER,
                team_mention TEXT,
                player_mention TEXT,
                game_id TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (game_id) REFERENCES games(game_id)
            )
            ''')
            
            # Create Comments table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS reddit_comments (
                comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                reddit_id TEXT UNIQUE NOT NULL,
                post_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                author TEXT,
                created_utc REAL NOT NULL,
                score INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (post_id) REFERENCES reddit_posts(post_id)
            )
            ''')
            
            # Create Sentiment Analysis table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS sentiment_analysis (
                sentiment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                post_id INTEGER,
                comment_id INTEGER,
                sentiment_score REAL NOT NULL,
                confidence REAL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (post_id) REFERENCES reddit_posts(post_id),
                FOREIGN KEY (comment_id) REFERENCES reddit_comments(comment_id),
                CHECK (post_id IS NOT NULL OR comment_id IS NOT NULL)
            )
            ''')
            
            # Create Predictions table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS predictions (
                prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL,
                home_team_sentiment REAL,
                away_team_sentiment REAL,
                home_win_probability REAL NOT NULL,
                prediction_timestamp TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (game_id) REFERENCES games(game_id)
            )
            ''')
            
            conn.commit()
            logger.info("Database tables initialized successfully")
    
    # Games table operations
    def insert_game(self, game_data: Dict[str, Any]) -> str:
        """
        Insert a new game into the games table.
        
        Args:
            game_data: Dictionary containing game information
            
        Returns:
            game_id: The ID of the inserted game
        """
        now = datetime.datetime.now().isoformat()
        
        # Ensure required fields are present
        required_fields = ['game_id', 'home_team', 'away_team', 'game_date', 'game_time']
        for field in required_fields:
            if field not in game_data:
                raise ValueError(f"Missing required field: {field}")
        
        # Add timestamps
        game_data['created_at'] = now
        game_data['updated_at'] = now
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Insert game
            placeholders = ', '.join(['?'] * len(game_data))
            columns = ', '.join(game_data.keys())
            values = list(game_data.values())
            
            query = f"INSERT INTO games ({columns}) VALUES ({placeholders})"
            cursor.execute(query, values)
            conn.commit()
            
            logger.info(f"Inserted game: {game_data['game_id']}")
            return game_data['game_id']
    
    def update_game(self, game_id: str, update_data: Dict[str, Any]) -> bool:
        """
        Update an existing game in the database.
        
        Args:
            game_id: The ID of the game to update
            update_data: Dictionary containing fields to update
            
        Returns:
            bool: True if successful, False otherwise
        """
        now = datetime.datetime.now().isoformat()
        
        # Add updated timestamp
        update_data['updated_at'] = now
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Build the SET clause for the UPDATE statement
            set_clause = ', '.join([f"{key} = ?" for key in update_data.keys()])
            values = list(update_data.values())
            values.append(game_id)  # For the WHERE clause
            
            query = f"UPDATE games SET {set_clause} WHERE game_id = ?"
            cursor.execute(query, values)
            conn.commit()
            
            if cursor.rowcount > 0:
                logger.info(f"Updated game: {game_id}")
                return True
            else:
                logger.warning(f"No game found with ID: {game_id}")
                return False
    
    def get_game(self, game_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a game by its ID.
        
        Args:
            game_id: The ID of the game to retrieve
            
        Returns:
            Dict containing game data or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM games WHERE game_id = ?", (game_id,))
            row = cursor.fetchone()
            
            if row:
                return dict(row)
            else:
                logger.warning(f"No game found with ID: {game_id}")
                return None
    
    def get_upcoming_games(self, days_ahead: int = 7) -> List[Dict[str, Any]]:
        """
        Retrieve upcoming games within the specified number of days.
        
        Args:
            days_ahead: Number of days to look ahead
            
        Returns:
            List of dictionaries containing game data
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            today = datetime.date.today()
            future_date = (today + datetime.timedelta(days=days_ahead)).isoformat()
            
            cursor.execute(
                "SELECT * FROM games WHERE game_date BETWEEN ? AND ? ORDER BY game_date, game_time",
                (today.isoformat(), future_date)
            )
            rows = cursor.fetchall()
            
            return [dict(row) for row in rows]
    
    # Players table operations
    def insert_player(self, player_data: Dict[str, Any]) -> int:
        """
        Insert a new player into the players table.
        
        Args:
            player_data: Dictionary containing player information
            
        Returns:
            player_id: The ID of the inserted player
        """
        now = datetime.datetime.now().isoformat()
        
        # Ensure required fields are present
        required_fields = ['name', 'team']
        for field in required_fields:
            if field not in player_data:
                raise ValueError(f"Missing required field: {field}")
        
        # Add timestamps
        player_data['created_at'] = now
        player_data['updated_at'] = now
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Insert player
            placeholders = ', '.join(['?'] * len(player_data))
            columns = ', '.join(player_data.keys())
            values = list(player_data.values())
            
            query = f"INSERT OR REPLACE INTO players ({columns}) VALUES ({placeholders})"
            cursor.execute(query, values)
            conn.commit()
            
            player_id = cursor.lastrowid
            logger.info(f"Inserted/updated player: {player_data['name']} (ID: {player_id})")
            return player_id
    
    def update_player_status(self, player_id: int, status: str) -> bool:
        """
        Update a player's status.
        
        Args:
            player_id: The ID of the player to update
            status: The new status value
            
        Returns:
            bool: True if successful, False otherwise
        """
        now = datetime.datetime.now().isoformat()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(
                "UPDATE players SET status = ?, updated_at = ? WHERE player_id = ?",
                (status, now, player_id)
            )
            conn.commit()
            
            if cursor.rowcount > 0:
                logger.info(f"Updated player status: ID {player_id} to {status}")
                return True
            else:
                logger.warning(f"No player found with ID: {player_id}")
                return False
    
    def get_players_by_team(self, team: str) -> List[Dict[str, Any]]:
        """
        Retrieve all players for a specific team.
        
        Args:
            team: The team name
            
        Returns:
            List of dictionaries containing player data
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM players WHERE team = ?", (team,))
            rows = cursor.fetchall()
            
            return [dict(row) for row in rows]
    
    # Reddit data operations
    def insert_reddit_post(self, post_data: Dict[str, Any]) -> int:
        """
        Insert a new Reddit post into the database.
        
        Args:
            post_data: Dictionary containing post information
            
        Returns:
            post_id: The ID of the inserted post
        """
        now = datetime.datetime.now().isoformat()
        
        # Ensure required fields are present
        required_fields = ['reddit_id', 'subreddit', 'title', 'created_utc']
        for field in required_fields:
            if field not in post_data:
                raise ValueError(f"Missing required field: {field}")
        
        # Add timestamp
        post_data['created_at'] = now
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Insert post
            placeholders = ', '.join(['?'] * len(post_data))
            columns = ', '.join(post_data.keys())
            values = list(post_data.values())
            
            query = f"INSERT OR IGNORE INTO reddit_posts ({columns}) VALUES ({placeholders})"
            cursor.execute(query, values)
            conn.commit()
            
            # Get the post_id (either the new one or the existing one if the post was already in the DB)
            cursor.execute("SELECT post_id FROM reddit_posts WHERE reddit_id = ?", (post_data['reddit_id'],))
            post_id = cursor.fetchone()['post_id']
            
            logger.info(f"Inserted/skipped Reddit post: {post_data['reddit_id']} (ID: {post_id})")
            return post_id
    
    def insert_reddit_comment(self, comment_data: Dict[str, Any]) -> int:
        """
        Insert a new Reddit comment into the database.
        
        Args:
            comment_data: Dictionary containing comment information
            
        Returns:
            comment_id: The ID of the inserted comment
        """
        now = datetime.datetime.now().isoformat()
        
        # Ensure required fields are present
        required_fields = ['reddit_id', 'post_id', 'content', 'created_utc']
        for field in required_fields:
            if field not in comment_data:
                raise ValueError(f"Missing required field: {field}")
        
        # Add timestamp
        comment_data['created_at'] = now
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Insert comment
            placeholders = ', '.join(['?'] * len(comment_data))
            columns = ', '.join(comment_data.keys())
            values = list(comment_data.values())
            
            query = f"INSERT OR IGNORE INTO reddit_comments ({columns}) VALUES ({placeholders})"
            cursor.execute(query, values)
            conn.commit()
            
            # Get the comment_id
            cursor.execute("SELECT comment_id FROM reddit_comments WHERE reddit_id = ?", (comment_data['reddit_id'],))
            comment_id = cursor.fetchone()['comment_id']
            
            logger.info(f"Inserted/skipped Reddit comment: {comment_data['reddit_id']} (ID: {comment_id})")
            return comment_id
    
    def get_reddit_posts_by_team(self, team: str, days_back: int = 7) -> List[Dict[str, Any]]:
        """
        Retrieve Reddit posts mentioning a specific team within a time period.
        
        Args:
            team: The team name to search for
            days_back: Number of days to look back
            
        Returns:
            List of dictionaries containing post data
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cutoff_time = (datetime.datetime.now() - datetime.timedelta(days=days_back)).timestamp()
            
            cursor.execute(
                "SELECT * FROM reddit_posts WHERE team_mention = ? AND created_utc > ? ORDER BY created_utc DESC",
                (team, cutoff_time)
            )
            rows = cursor.fetchall()
            
            return [dict(row) for row in rows]
    
    # Sentiment analysis operations
    def insert_sentiment_analysis(self, sentiment_data: Dict[str, Any]) -> int:
        """
        Insert a new sentiment analysis record into the database.
        
        Args:
            sentiment_data: Dictionary containing sentiment analysis data
            
        Returns:
            sentiment_id: The ID of the inserted record
        """
        now = datetime.datetime.now().isoformat()
        
        # Ensure required fields are present
        required_fields = ['entity_type', 'entity_id', 'sentiment_score']
        for field in required_fields:
            if field not in sentiment_data:
                raise ValueError(f"Missing required field: {field}")
        
        # Ensure at least one of post_id or comment_id is present
        if 'post_id' not in sentiment_data and 'comment_id' not in sentiment_data:
            raise ValueError("Either post_id or comment_id must be provided")
        
        # Add timestamp
        sentiment_data['created_at'] = now
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Insert sentiment analysis
            placeholders = ', '.join(['?'] * len(sentiment_data))
            columns = ', '.join(sentiment_data.keys())
            values = list(sentiment_data.values())
            
            query = f"INSERT INTO sentiment_analysis ({columns}) VALUES ({placeholders})"
            cursor.execute(query, values)
            conn.commit()
            
            sentiment_id = cursor.lastrowid
            logger.info(f"Inserted sentiment analysis for {sentiment_data['entity_type']} {sentiment_data['entity_id']} (ID: {sentiment_id})")
            return sentiment_id
    
    def get_team_sentiment(self, team: str, days_back: int = 7) -> Tuple[float, int]:
        """
        Calculate the average sentiment score for a team over a time period.
        
        Args:
            team: The team name
            days_back: Number of days to look back
            
        Returns:
            Tuple of (average sentiment score, number of sentiment records)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cutoff_time = datetime.datetime.now() - datetime.timedelta(days=days_back)
            cutoff_str = cutoff_time.isoformat()
            
            cursor.execute(
                """
                SELECT AVG(sentiment_score) as avg_sentiment, COUNT(*) as count
                FROM sentiment_analysis
                WHERE entity_type = 'team' AND entity_id = ? AND created_at > ?
                """,
                (team, cutoff_str)
            )
            result = cursor.fetchone()
            
            if result and result['count'] > 0:
                return (result['avg_sentiment'], result['count'])
            else:
                logger.warning(f"No sentiment data found for team {team}")
                return (0.0, 0)
    
    # Prediction operations
    def insert_prediction(self, prediction_data: Dict[str, Any]) -> int:
        """
        Insert a new game prediction into the database.
        
        Args:
            prediction_data: Dictionary containing prediction information
            
        Returns:
            prediction_id: The ID of the inserted prediction
        """
        now = datetime.datetime.now().isoformat()
        
        # Ensure required fields are present
        required_fields = ['game_id', 'home_win_probability', 'prediction_timestamp']
        for field in required_fields:
            if field not in prediction_data:
                raise ValueError(f"Missing required field: {field}")
        
        # Add timestamp
        prediction_data['created_at'] = now
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Insert prediction
            placeholders = ', '.join(['?'] * len(prediction_data))
            columns = ', '.join(prediction_data.keys())
            values = list(prediction_data.values())
            
            query = f"INSERT INTO predictions ({columns}) VALUES ({placeholders})"
            cursor.execute(query, values)
            conn.commit()
            
            prediction_id = cursor.lastrowid
            logger.info(f"Inserted prediction for game {prediction_data['game_id']} (ID: {prediction_id})")
            return prediction_id
    
    def get_latest_prediction(self, game_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve the latest prediction for a specific game.
        
        Args:
            game_id: The ID of the game
            
        Returns:
            Dict containing prediction data or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM predictions
                WHERE game_id = ?
                ORDER BY prediction_timestamp DESC
                LIMIT 1
                """,
                (game_id,)
            )
            row = cursor.fetchone()
            
            if row:
                return dict(row)
            else:
                logger.warning(f"No prediction found for game: {game_id}")
                return None
    
    def update_prediction_results(self, game_id: str, actual_result: str) -> bool:
        """
        Update the actual result of a game in the games table.
        
        Args:
            game_id: The ID of the game
            actual_result: The actual result of the game
            
        Returns:
            bool: True if successful, False otherwise
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.datetime.now().isoformat()
            
            cursor.execute(
                "UPDATE games SET actual_result = ?, updated_at = ? WHERE game_id = ?",
                (actual_result, now, game_id)
            )
            conn.commit()
            
            if cursor.rowcount > 0:
                logger.info(f"Updated game result for {game_id}: {actual_result}")
                return True
            else:
                logger.warning(f"No game found with ID: {game_id}")
                return False