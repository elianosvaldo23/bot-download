import sqlite3
from datetime import datetime, timedelta

class Database:
    def __init__(self, db_file="multimedia_tv.db"):
        self.db_file = db_file
        self.admin_id = 1742433244
        self.create_tables()
    
    def create_tables(self):
        """Create necessary tables if they don't exist"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            plan_type TEXT DEFAULT 'basic',
            plan_expiry TEXT NULL,
            daily_searches INTEGER DEFAULT 0,
            daily_searches_limit INTEGER DEFAULT 3,
            daily_requests INTEGER DEFAULT 0,
            daily_requests_limit INTEGER DEFAULT 1,
            can_forward INTEGER DEFAULT 0,
            join_date TEXT,
            last_active TEXT,
            balance INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0
        )
        ''')
        
        # Referrals table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            date TEXT,
            FOREIGN KEY (referrer_id) REFERENCES users (user_id),
            FOREIGN KEY (referred_id) REFERENCES users (user_id)
        )
        ''')
        
        # Gift codes table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS gift_codes (
            code TEXT PRIMARY KEY,
            plan_type TEXT,
            max_uses INTEGER,
            uses INTEGER DEFAULT 0,
            created_by INTEGER,
            created_at TEXT,
            FOREIGN KEY (created_by) REFERENCES users (user_id)
        )
        ''')
        
        # Statistics table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS statistics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            total_searches INTEGER DEFAULT 0,
            total_requests INTEGER DEFAULT 0,
            last_updated TEXT
        )
        ''')
        
        # Content table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS content (
            content_id INTEGER PRIMARY KEY,
            name TEXT,
            content_type TEXT,
            message_id INTEGER,
            added_by INTEGER,
            added_at TEXT,
            FOREIGN KEY (added_by) REFERENCES users (user_id)
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_user(self, user_id, username, first_name, last_name=None):
        """Add a new user to the database"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, join_date, last_active) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, first_name, last_name, now, now)
        )
        
        conn.commit()
        conn.close()
    
    def get_user(self, user_id):
        """Get user data from the database"""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user_data = cursor.fetchone()
        
        conn.close()
        
        if user_data:
            return dict(user_data)
        return None
    
    def user_exists(self, user_id):
        """Check if a user exists in the database"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()[0] > 0
        
        conn.close()
        return result
    
    def get_admin_id(self):
        """Return the admin ID"""
        return self.admin_id
    
    def get_user_by_username(self, username):
        """Get user data by username"""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user_data = cursor.fetchone()
        
        conn.close()
        
        if user_data:
            return dict(user_data)
        return None
    
    def get_user_id_by_username(self, username):
        """Get user_id by username"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute("SELECT user_id FROM users WHERE username = ?", (username,))
        result = cursor.fetchone()
        
        conn.close()
        
        if result:
            return result[0]
        return None
    
    def update_plan(self, user_id, plan_type, expiry_date):
        """Update a user's plan"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Define plan limits
        plan_limits = {
            'basic': (3, 1, 0),  # searches, requests, can_forward
            'pro': (15, 2, 0),
            'plus': (50, 10, 1),
            'ultra': (999, 999, 1)  # Using 999 for "unlimited"
        }
        
        searches, requests, can_forward = plan_limits.get(plan_type, (3, 1, 0))
        
        if expiry_date:
            # Format date to string
            expiry_str = expiry_date.strftime("%Y-%m-%d %H:%M:%S")
            
            cursor.execute(
                """UPDATE users 
                   SET plan_type = ?, plan_expiry = ?, 
                   daily_searches_limit = ?, daily_requests_limit = ?, can_forward = ? 
                   WHERE user_id = ?""",
                (plan_type, expiry_str, searches, requests, can_forward, user_id)
            )
        else:
            # No expiry date (for basic plan)
            cursor.execute(
                """UPDATE users 
                   SET plan_type = ?, plan_expiry = NULL, 
                   daily_searches_limit = ?, daily_requests_limit = ?, can_forward = ? 
                   WHERE user_id = ?""",
                (plan_type, searches, requests, can_forward, user_id)
            )
        
        conn.commit()
        conn.close()
    
    def remove_plan(self, user_id):
        """Reset user to basic plan"""
        self.update_plan(user_id, 'basic', None)
    
    def ban_user(self, user_id):
        """Ban a user"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
        
        conn.commit()
        conn.close()
    
    def is_user_banned(self, user_id):
        """Check if a user is banned"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        
        conn.close()
        
        if result:
            return result[0] == 1
        return False
    
    def get_daily_usage(self, user_id):
        """Get user's daily search usage"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute("SELECT daily_searches FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        
        conn.close()
        
        if result:
            return result[0]
        return 0
    
    def increment_daily_usage(self, user_id):
        """Increment user's daily search usage and check if limit is reached"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Get current usage and limit
        cursor.execute(
            "SELECT daily_searches, daily_searches_limit FROM users WHERE user_id = ?", 
            (user_id,)
        )
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return False
        
        current_usage, limit = result
        
        # Check if user has reached the limit
        if current_usage >= limit:
            conn.close()
            return False
        
        # Increment usage
        cursor.execute(
            "UPDATE users SET daily_searches = daily_searches + 1, last_active = ? WHERE user_id = ?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id)
        )
        
        # Update statistics
        cursor.execute(
            "UPDATE statistics SET total_searches = total_searches + 1, last_updated = ? WHERE id = 1",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),)
        )
        if cursor.rowcount == 0:
            cursor.execute(
                "INSERT INTO statistics (id, total_searches, last_updated) VALUES (1, 1, ?)",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),)
            )
        
        conn.commit()
        conn.close()
        
        return True
    
    def update_request_count(self, user_id):
        """Update a user's daily request count"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute(
            "UPDATE users SET daily_requests = daily_requests + 1, last_active = ? WHERE user_id = ?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id)
        )
        
        # Update total requests in statistics
        cursor.execute(
            "UPDATE statistics SET total_requests = total_requests + 1, last_updated = ? WHERE id = 1",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),)
        )
        
        # If no row was updated in statistics, insert one
        if cursor.rowcount == 0:
            cursor.execute(
                "INSERT INTO statistics (total_searches, total_requests, last_updated) VALUES (0, 1, ?)",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),)
            )
        
        conn.commit()
        conn.close()
    
    def get_requests_left(self, user_id):
        """Get the number of requests a user has left today"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT daily_requests, daily_requests_limit FROM users WHERE user_id = ?", 
            (user_id,)
        )
        result = cursor.fetchone()
        
        conn.close()
        
        if result:
            current, limit = result
            return max(0, limit - current)
        return 0
    
    def add_gift_code(self, code, plan_type, max_uses, created_by=None):
        """Add a gift code to the database"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO gift_codes (code, plan_type, max_uses, uses, created_by, created_at) VALUES (?, ?, ?, 0, ?, ?)",
            (code, plan_type, max_uses, created_by or self.admin_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        
        conn.commit()
        conn.close()
    
    def get_gift_code(self, code):
        """Get gift code data if it exists and has uses left"""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM gift_codes WHERE code = ? AND uses < max_uses", (code,))
        row = cursor.fetchone()
        
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def update_gift_code_usage(self, code):
        """Update the usage count of a gift code"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute("UPDATE gift_codes SET uses = uses + 1 WHERE code = ?", (code,))
        
        conn.commit()
        conn.close()
    
    def reset_daily_limits(self):
        """Reset daily search and request limits for all users"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute("UPDATE users SET daily_searches = 0, daily_requests = 0")
        
        conn.commit()
        conn.close()
    
    def get_expired_plans(self):
        """Get users with expired plans"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "SELECT user_id FROM users WHERE plan_type != 'basic' AND plan_expiry < ?",
            (now,)
        )
        
        expired_user_ids = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        return expired_user_ids
    
    def get_total_users(self):
        """Get total number of users"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        
        conn.close()
        return count
    
    def get_active_users(self, days=7):
        """Get number of active users in the last X days"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "SELECT COUNT(*) FROM users WHERE last_active > ?",
            (cutoff_date,)
        )
        count = cursor.fetchone()[0]
        
        conn.close()
        return count
    
    def get_premium_users(self):
        """Get number of users with premium plans"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE plan_type != 'basic'")
        count = cursor.fetchone()[0]
        
        conn.close()
        return count
    
    def get_users_by_plan(self, plan_type):
        """Get number of users with a specific plan"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE plan_type = ?", (plan_type,))
        count = cursor.fetchone()[0]
        
        conn.close()
        return count
    
    def get_total_searches(self):
        """Get total number of searches"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute("SELECT total_searches FROM statistics WHERE id = 1")
        result = cursor.fetchone()
        
        conn.close()
        
        if result:
            return result[0]
        return 0
    
    def get_total_requests(self):
        """Get total number of requests"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute("SELECT total_requests FROM statistics WHERE id = 1")
        result = cursor.fetchone()
        
        conn.close()
        
        if result:
            return result[0]
        return 0
    
    def get_all_user_ids(self):
        """Get all user IDs"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute("SELECT user_id FROM users WHERE is_banned = 0")
        user_ids = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        return user_ids
    
    def get_all_users(self):
        """Get all users"""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE is_banned = 0")
        users = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        return users
    
    def get_stats(self):
        """Get bot statistics"""
        return {
            'total_users': self.get_total_users(),
            'premium_users': self.get_premium_users(),
            'searches_today': 0,  # Would need additional query
            'total_searches': self.get_total_searches()
        }
    
    def add_referral(self, referrer_id, referred_id):
        """Add a referral to the database and update referrer's balance"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Add referral record
        cursor.execute(
            "INSERT INTO referrals (referrer_id, referred_id, date) VALUES (?, ?, ?)",
            (referrer_id, referred_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        
        # Update referrer's balance
        cursor.execute(
            "UPDATE users SET balance = balance + 1 WHERE user_id = ?",
            (referrer_id,)
        )
        
        conn.commit()
        conn.close()
    
    def is_referred(self, user_id):
        """Check if a user has already been referred"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referred_id = ?", (user_id,))
        result = cursor.fetchone()[0] > 0
        
        conn.close()
        return result
    
    def get_referral_count(self, user_id):
        """Get the number of referrals a user has made"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
        count = cursor.fetchone()[0]
        
        conn.close()
        return count
