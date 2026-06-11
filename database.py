import sqlite3

DB_NAME = "supershopper.db"

def init_db():
    """Creates the database tables for both history tracking and user profiles."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. NEW: Create a table to store registered user credentials safely
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            tier TEXT DEFAULT 'free'
        )
    """)
    
    # 2. UPGRADED: Create history table with a user_id link column
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            budget REAL,
            initial_total REAL,
            final_total REAL,
            triage_applied INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    
    # Insert some dummy testing accounts automatically if they don't exist yet
    try:
        cursor.execute("INSERT INTO users (username, password_hash, tier) VALUES (?, ?, ?)", ("free_user", "password123", "free"))
        cursor.execute("INSERT INTO users (username, password_hash, tier) VALUES (?, ?, ?)", ("premium_user", "secure456", "premium"))
    except sqlite3.IntegrityError:
        pass # Accounts already exist
        
    conn.commit()
    conn.close()
    print("💾 Database upgraded with User Account Profiles!")

def save_optimization_record(user_id: int, budget: float, initial: float, final: float, triaged: bool):
    """Saves a calculation log attached to a specific user id."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO history (user_id, budget, initial_total, final_total, triage_applied)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, budget, initial, final, 1 if triaged else 0))
    conn.commit()
    conn.close()

def get_history_logs(user_id: int = None):
    """Fetches past runs. Filters by user_id if logged in, or shows all for admin."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if user_id:
        cursor.execute("SELECT id, timestamp, budget, initial_total, final_total, triage_applied FROM history WHERE user_id = ? ORDER BY id DESC", (user_id,))
    else:
        cursor.execute("SELECT id, timestamp, budget, initial_total, final_total, triage_applied FROM history ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def verify_user_login(username, password):
    """Checks if username and password match. Returns user dict or None."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, tier FROM users WHERE username = ? AND password_hash = ?", (username, password))
    user = cursor.fetchone()
    conn.close()
    if user:
        return {"id": user[0], "username": user[1], "tier": user[2]}
    return None