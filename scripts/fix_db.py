import sqlite3

def fix():
    conn = sqlite3.connect("expense_tracker.db")
    c = conn.cursor()
    c.execute("UPDATE expenses SET currency = 'USD'")
    conn.commit()
    print(f"Updated {conn.total_changes} rows to USD.")
    conn.close()

if __name__ == "__main__":
    fix()
