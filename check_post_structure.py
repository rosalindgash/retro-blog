import sqlite3

with sqlite3.connect("blog.db") as conn:
    cursor = conn.execute("PRAGMA table_info(posts);")
    for row in cursor.fetchall():
        print(row)
