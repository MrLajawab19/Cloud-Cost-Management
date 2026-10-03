import sqlite3

def main():
    conn = sqlite3.connect("d:/Cloud Cost Management/backend/cloud_cost.db")
    cursor = conn.cursor()
    
    try:
        cursor.execute("ALTER TABLE recommendations ADD COLUMN upfront_cost_usd FLOAT;")
        print("Added upfront_cost_usd")
    except sqlite3.OperationalError as e:
        print("upfront_cost_usd:", e)

    try:
        cursor.execute("ALTER TABLE recommendations ADD COLUMN payback_days INTEGER;")
        print("Added payback_days")
    except sqlite3.OperationalError as e:
        print("payback_days:", e)
        
    conn.commit()
    
    cursor.execute("PRAGMA table_info(recommendations);")
    columns = cursor.fetchall()
    print("--- PRAGMA table_info(recommendations) ---")
    for col in columns:
        print(col)
        
    conn.close()

if __name__ == "__main__":
    main()
