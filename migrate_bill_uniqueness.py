"""
Migration script to add uniqueness constraint for Bill model
Ensures (student_id, month, year, mess_id) uniqueness
"""
import sqlite3
import os

def migrate_bill_uniqueness():
    db_path = os.path.join('instance', 'mess_management.db')
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        print("Starting Bill uniqueness constraint migration...")
        
        # Check if the unique constraint already exists
        cursor.execute("PRAGMA index_list('bill')")
        indexes = cursor.fetchall()
        
        # Check if unique index already exists
        for index in indexes:
            cursor.execute(f"PRAGMA index_info('{index[1]}')")
            columns = [col[2] for col in cursor.fetchall()]
            if set(columns) == {'student_id', 'month', 'year', 'mess_id'}:
                print("✓ Unique constraint already exists")
                return
        
        # Find and remove duplicate bills (keep the most recent one)
        print("Checking for duplicate bills...")
        cursor.execute("""
            SELECT student_id, month, year, mess_id, COUNT(*) as cnt, GROUP_CONCAT(id) as ids
            FROM bill
            GROUP BY student_id, month, year, mess_id
            HAVING cnt > 1
        """)
        
        duplicates = cursor.fetchall()
        
        if duplicates:
            print(f"Found {len(duplicates)} sets of duplicate bills. Removing duplicates...")
            for dup in duplicates:
                student_id, month, year, mess_id, count, ids_str = dup
                ids = [int(x) for x in ids_str.split(',')]
                # Keep the largest ID (most recent), delete others
                ids_to_delete = ids[:-1]
                
                for bill_id in ids_to_delete:
                    print(f"  Deleting duplicate bill ID {bill_id} (student={student_id}, month={month}, year={year})")
                    # Delete associated payments first
                    cursor.execute("DELETE FROM payment WHERE bill_id = ?", (bill_id,))
                    # Delete the bill
                    cursor.execute("DELETE FROM bill WHERE id = ?", (bill_id,))
        else:
            print("✓ No duplicate bills found")
        
        # Create unique index
        print("Creating unique constraint...")
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_bill_unique 
            ON bill(student_id, month, year, mess_id)
        """)
        
        conn.commit()
        print("✓ Bill uniqueness constraint migration completed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"✗ Error during migration: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_bill_uniqueness()
