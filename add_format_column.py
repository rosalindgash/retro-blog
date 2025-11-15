import sqlite3

DATABASE = 'blog.db'

with sqlite3.connect(DATABASE) as conn:
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(posts)")
    columns = [col[1] for col in cursor.fetchall()]

    if 'format' not in columns:
        conn.execute("ALTER TABLE posts ADD COLUMN format TEXT DEFAULT 'html'")
        conn.commit()
        print("Format column added to posts table.")
    else:
        print("Format column already exists.")
