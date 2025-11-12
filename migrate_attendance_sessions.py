"""
Migration script to add AttendanceSession table and update Attendance table
Run this script to update your database schema
"""

from app import app, db, AttendanceSession, Attendance
from sqlalchemy import text

def migrate():
    with app.app_context():
        print("Starting database migration...")
        
        try:
            # Create AttendanceSession table
            print("Creating AttendanceSession table...")
            db.create_all()
            print("✓ AttendanceSession table created")
            
            # Check if session_id column exists in Attendance table
            print("Checking Attendance table...")
            inspector = db.inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('attendance')]
            
            if 'session_id' not in columns:
                print("Adding session_id column to Attendance table...")
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE attendance ADD COLUMN session_id INTEGER'))
                    conn.commit()
                print("✓ session_id column added")
            else:
                print("✓ session_id column already exists")
            
            print("\n✅ Migration completed successfully!")
            print("\nYou can now:")
            print("1. Generate QR codes for attendance sessions")
            print("2. Students can scan QR codes from their phones")
            print("3. Attendance will be marked automatically")
            
        except Exception as e:
            print(f"\n❌ Migration failed: {str(e)}")
            print("Please check your database and try again.")
            raise

if __name__ == '__main__':
    migrate()
