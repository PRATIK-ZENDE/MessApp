"""
Cleanup script to remove deprecated Settings keys after multi-mess migration
These settings are now stored in the Mess model
"""
import sqlite3
import os

def cleanup_deprecated_settings():
    db_path = os.path.join('instance', 'mess_management.db')
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        print("Starting Settings cleanup...")
        
        # List of deprecated keys that are now in Mess model
        deprecated_keys = ['daily_meal_rate', 'upi_id', 'upi_name']
        
        for key in deprecated_keys:
            cursor.execute("SELECT * FROM settings WHERE key = ?", (key,))
            existing = cursor.fetchone()
            
            if existing:
                print(f"  Removing deprecated setting: {key} = {existing[1]}")
                cursor.execute("DELETE FROM settings WHERE key = ?", (key,))
            else:
                print(f"  ✓ Setting '{key}' already removed or doesn't exist")
        
        conn.commit()
        print("✓ Settings cleanup completed successfully!")
        print("\nNote: These settings are now managed in the Mess model.")
        print("You can update them via the Settings page, which will modify the Mess record.")
        
    except Exception as e:
        conn.rollback()
        print(f"✗ Error during cleanup: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    cleanup_deprecated_settings()
