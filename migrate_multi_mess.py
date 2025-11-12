"""
Migration script to introduce multi-mess support.
Adds Mess table and mess_id columns to existing tables if they don't exist.
Safe to run multiple times.
"""
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join('instance','mess.db')

def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return column in [row[1] for row in cursor.fetchall()]

def table_exists(cursor, table):
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cursor.fetchone() is not None

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}. Run app once to create it.")
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    try:
        print("== Multi-mess Migration ==")
        # 1. Create Mess table if missing
        if not table_exists(cur, 'mess'):
            print("Creating 'mess' table...")
            cur.execute("""
                CREATE TABLE mess (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(150) UNIQUE NOT NULL,
                    daily_meal_rate FLOAT NOT NULL DEFAULT 100.0,
                    upi_id VARCHAR(150),
                    upi_name VARCHAR(150),
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
        else:
            print("'mess' table already exists.")

        # 2. Add mess_id columns
        targets = ['user','student','attendance_session','bill','payment']
        for table in targets:
            if not column_exists(cur, table, 'mess_id'):
                print(f"Adding mess_id to {table}...")
                cur.execute(f"ALTER TABLE {table} ADD COLUMN mess_id INTEGER REFERENCES mess(id)")
            else:
                print(f"mess_id already exists on {table}.")

        # 3. Seed default mess and backfill null mess_id
        cur.execute("SELECT id FROM mess LIMIT 1")
        row = cur.fetchone()
        if not row:
            print("Seeding initial mess record...")
            cur.execute("INSERT INTO mess (name, daily_meal_rate, upi_id, upi_name, is_active, created_at) VALUES (?,?,?,?,1,?)",
                        ("Default Mess", 100.0, "mess@oksbi", "Mess Management", datetime.utcnow().isoformat()))
            default_id = cur.lastrowid
        else:
            default_id = row[0]
            print(f"Using existing mess id {default_id} for backfill.")

        for table in targets:
            print(f"Backfilling {table}.mess_id where NULL...")
            cur.execute(f"UPDATE {table} SET mess_id = ? WHERE mess_id IS NULL", (default_id,))

        conn.commit()
        print("Migration complete.")

    except Exception as e:
        conn.rollback()
        print("Migration failed:", e)
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
