"""
Database migration script to add new columns to Student table
This script adds roll_no, department, and password_hash columns
"""

import sqlite3
import os
from werkzeug.security import generate_password_hash

# Path to database
DB_PATH = 'instance/mess.db'

def migrate_database():
    print("=" * 60)
    print("Database Migration: Adding Student Authentication")
    print("=" * 60)
    
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(student)")
        columns = [column[1] for column in cursor.fetchall()]
        print(f"Existing columns: {columns}")
        
        # Add roll_no column if it doesn't exist
        if 'roll_no' not in columns:
            print("\n➕ Adding 'roll_no' column...")
            cursor.execute("ALTER TABLE student ADD COLUMN roll_no VARCHAR(50)")
            print("   ✅ Added 'roll_no' column")
        else:
            print("\n⚠️  'roll_no' column already exists")
        
        # Add department column if it doesn't exist
        if 'department' not in columns:
            print("\n➕ Adding 'department' column...")
            cursor.execute("ALTER TABLE student ADD COLUMN department VARCHAR(100)")
            print("   ✅ Added 'department' column")
        else:
            print("\n⚠️  'department' column already exists")
        
        # Add password_hash column if it doesn't exist
        if 'password_hash' not in columns:
            print("\n➕ Adding 'password_hash' column...")
            cursor.execute("ALTER TABLE student ADD COLUMN password_hash VARCHAR(200)")
            print("   ✅ Added 'password_hash' column")
        else:
            print("\n⚠️  'password_hash' column already exists")
        
        # Now update existing students
        print("\n" + "=" * 60)
        print("Updating Existing Student Records")
        print("=" * 60)
        
        cursor.execute("SELECT id, name, roll_no, password_hash FROM student")
        students = cursor.fetchall()
        
        if not students:
            print("No students found in database.")
        else:
            print(f"Found {len(students)} students to update:\n")
            
            default_password_hash = generate_password_hash("password123")
            
            for student_id, name, roll_no, password_hash in students:
                updates = []
                
                # Set roll_no if missing
                if not roll_no:
                    new_roll_no = f"STU{str(student_id).zfill(4)}"
                    cursor.execute("UPDATE student SET roll_no = ? WHERE id = ?", (new_roll_no, student_id))
                    updates.append(f"roll_no: {new_roll_no}")
                
                # Set password if missing
                if not password_hash:
                    cursor.execute("UPDATE student SET password_hash = ? WHERE id = ?", (default_password_hash, student_id))
                    updates.append("password: password123")
                
                # Set default department if missing
                cursor.execute("UPDATE student SET department = 'General' WHERE id = ? AND (department IS NULL OR department = '')", (student_id,))
                
                if updates:
                    print(f"  ✅ Updated {name}: {', '.join(updates)}")
        
        # Commit all changes
        conn.commit()
        
        print("\n" + "=" * 60)
        print("✅ Migration completed successfully!")
        print("=" * 60)
        print("\nDefault Student Credentials:")
        print("  - Roll Number: STU#### (e.g., STU0001, STU0002)")
        print("  - Password: password123")
        print("\n⚠️  Students should change their password after first login!")
        print("=" * 60)
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error during migration: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_database()
