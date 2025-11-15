import sqlite3

with sqlite3.connect("blog.db") as conn:
    cursor = conn.execute("SELECT id, title, tags FROM posts")
    for row in cursor.fetchall():
        print(f"Post ID: {row[0]} | Title: {row[1]} | Tags: {row[2]}")
