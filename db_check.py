from app import app, db

def check_db():
    with app.app_context():
        # Inspect the database
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        print("\nDatabase Tables:", tables)

        # Check Bill table columns
        if 'bill' in tables:
            print("\nBill Table Columns:")
            for column in inspector.get_columns('bill'):
                print(f"{column['name']}: {column['type']}")

if __name__ == '__main__':
    check_db()