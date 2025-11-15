import sqlite3

DATABASE = 'blog.db'

with sqlite3.connect(DATABASE) as conn:
    try:
        conn.execute("ALTER TABLE posts ADD COLUMN tags TEXT;")
        print("Tags column added successfully.")
    except sqlite3.OperationalError as e:
        print("Error:", e)
