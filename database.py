import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict

class Database:
    def __init__(self, db_file: str = "bot.db"):
        self.db_file = db_file
        self.init_db()
        # Inicialización de la base de datos
        self.admin_id = 1742433244  # ID del administrador (puedes cambiarlo)

    def get_admin_id(self):
        """Retorna el ID del administrador."""
        return self.admin_id

    # Otros métodos de la clase Database...
    
    def init_db(self):
        """Initialize database tables."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        
        # Create users table
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                registered_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                plan_type TEXT DEFAULT 'free',
                plan_expiry TIMESTAMP,
                daily_searches_limit INTEGER DEFAULT 3,
                can_forward BOOLEAN DEFAULT 0
            )
        ''')
        
        # Create daily usage table
        c.execute('''
            CREATE TABLE IF NOT EXISTS daily_usage (
                user_id INTEGER,
                date DATE,
                searches_count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, date),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user information."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        
        c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        
        if result:
            return {
                'user_id': result[0],
                'username': result[1],
                'first_name': result[2],
                'last_name': result[3],
                'registered_date': result[4],
                'plan_type': result[5],
                'plan_expiry': result[6],
                'daily_searches_limit': result[7],
                'can_forward': bool(result[8])
            }
        return None
    
    def add_user(self, user_id: int, username: str, first_name: str, last_name: str):
        """Add or update user."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        
        c.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name))
        
        conn.commit()
        conn.close()
    
    def get_daily_usage(self, user_id: int) -> int:
        """Get user's daily search count."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        
        today = datetime.now().date()
        c.execute('''
            SELECT searches_count 
            FROM daily_usage 
            WHERE user_id = ? AND date = ?
        ''', (user_id, today))
        
        result = c.fetchone()
        conn.close()
        
        return result[0] if result else 0
    
    def increment_daily_usage(self, user_id: int) -> bool:
        """Increment daily usage. Returns False if limit exceeded."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        
        user_data = self.get_user(user_id)
        if not user_data:
            conn.close()
            return False
            
        limit = user_data['daily_searches_limit']
        current = self.get_daily_usage(user_id)
        
        if current >= limit:
            conn.close()
            return False
            
        today = datetime.now().date()
        c.execute('''
            INSERT OR REPLACE INTO daily_usage (user_id, date, searches_count)
            VALUES (?, ?, ?)
        ''', (user_id, today, current + 1))
        
        conn.commit()
        conn.close()
        return True
    
    def update_plan(self, user_id: int, plan_type: str, days: int, searches: int):
        """Update user's plan."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        
        expiry = datetime.now() + timedelta(days=days)
        can_forward = plan_type != 'free'
        
        c.execute('''
            UPDATE users 
            SET plan_type = ?, 
                plan_expiry = ?,
                daily_searches_limit = ?,
                can_forward = ?
            WHERE user_id = ?
        ''', (plan_type, expiry, searches, can_forward, user_id))
        
        conn.commit()
        conn.close()
    
    def remove_plan(self, user_id: int):
        """Reset user to free plan."""
        self.update_plan(user_id, 'free', 0, 3)

    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Obtener información del usuario por nombre de usuario."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        
        c.execute('SELECT * FROM users WHERE username = ?', (username,))
        result = c.fetchone()
        conn.close()
        
        if result:
            return {
                'user_id': result[0],
                'username': result[1],
                'first_name': result[2],
                'last_name': result[3],
                'registered_date': result[4],
                'plan_type': result[5],
                'plan_expiry': result[6],
                'daily_searches_limit': result[7],
                'can_forward': bool(result[8])
            }
        return None
    
    def get_all_users(self) -> List[Dict]:
        """Get all users for announcements."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        
        c.execute('SELECT user_id FROM users')
        users = [{'user_id': row[0]} for row in c.fetchall()]
        
        conn.close()
        return users

    def get_stats(self) -> Dict:
        """Get bot statistics."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        
        # Get total users
        c.execute('SELECT COUNT(*) FROM users')
        total_users = c.fetchone()[0]
        
        # Get premium users
        c.execute("SELECT COUNT(*) FROM users WHERE plan_type != 'free'")
        premium_users = c.fetchone()[0]
        
        # Get today's searches
        today = datetime.now().date()
        c.execute('''
            SELECT COALESCE(SUM(searches_count), 0)
            FROM daily_usage 
            WHERE date = ?
        ''', (today,))
        searches_today = c.fetchone()[0]
        
        # Get total searches
        c.execute('SELECT COALESCE(SUM(searches_count), 0) FROM daily_usage')
        total_searches = c.fetchone()[0]
        
        conn.close()
        
        return {
            'total_users': total_users,
            'premium_users': premium_users,
            'searches_today': searches_today,
            'total_searches': total_searches
    }
