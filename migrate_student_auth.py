"""
Migration script to add student authentication fields to the database
Run this script to update existing students with password and roll_no fields
"""

from app import app, db, Student
from werkzeug.security import generate_password_hash

def migrate_students():
    with app.app_context():
        print("Starting student table migration...")
        
        # Get all students
        students = Student.query.all()
        
        if not students:
            print("No students found in database.")
            return
        
        print(f"Found {len(students)} students. Updating records...")
        
        updated_count = 0
        for student in students:
            try:
                # Add roll_no if missing (use id as fallback)
                if not student.roll_no:
                    student.roll_no = f"STU{str(student.id).zfill(4)}"
                    print(f"  - Set roll_no for {student.name}: {student.roll_no}")
                
                # Add default password if missing
                if not student.password_hash:
                    # Default password is "password123"
                    student.password_hash = generate_password_hash("password123")
                    print(f"  - Set default password for {student.name} (password123)")
                
                # Add department if missing
                if not hasattr(student, 'department') or not student.department:
                    student.department = "General"
                
                updated_count += 1
            except Exception as e:
                print(f"  - Error updating {student.name}: {str(e)}")
        
        # Commit changes
        try:
            db.session.commit()
            print(f"\n✅ Successfully updated {updated_count} students!")
            print("\nDefault credentials:")
            print("  - Roll Number: STU#### (where #### is the student ID)")
            print("  - Password: password123")
            print("\nStudents should change their password after first login.")
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Error committing changes: {str(e)}")

if __name__ == '__main__':
    print("=" * 60)
    print("Student Authentication Migration")
    print("=" * 60)
    migrate_students()
    print("=" * 60)
