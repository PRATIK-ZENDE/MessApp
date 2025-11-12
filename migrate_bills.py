from app import db, app
from datetime import datetime
from sqlalchemy import text # type: ignore

def upgrade_bill_table():
    # Drop existing table and recreate with new schema
    with app.app_context():
        # Backup existing data
        result = db.session.execute(text('SELECT * FROM bill'))
        old_bills = [dict(row) for row in result]
        
        # Drop old table
        db.session.execute(text('DROP TABLE IF EXISTS bill'))
        
        # Create new table with updated schema
        db.create_all()
        
        # Restore data with new fields
        for bill in old_bills:
            sql = text('''
                INSERT INTO bill (
                    id, student_id, month, year, amount, paid, 
                    generated_on, days_present, daily_rate
                ) VALUES (
                    :id, :student_id, :month, :year, :amount, :paid,
                    :generated_on, :days_present, :daily_rate
                )
            ''')
            db.session.execute(sql, {
                'id': bill['id'],
                'student_id': bill['student_id'],
                'month': bill['month'],
                'year': bill['year'],
                'amount': bill['amount'],
                'paid': bill['paid'],
                'generated_on': bill.get('generated_date', datetime.now()),
                'days_present': bill.get('days_present', 0),
                'daily_rate': bill.get('daily_rate', 100.0)
            })
            
        db.session.commit()

def run_migration():
    from app import app
    with app.app_context():
        try:
            upgrade_bill_table()
            print("Migration completed successfully!")
        except Exception as e:
            print(f"Error during migration: {e}")
            db.session.rollback()

if __name__ == '__main__':
    run_migration()