import sqlite3
import os

path = 'user_progress.db'
print('cwd=', os.getcwd())
print('exists=', os.path.exists(path))
if not os.path.exists(path):
    raise SystemExit(1)

conn = sqlite3.connect(path)
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print('tables=', cur.fetchall())
cur.execute('PRAGMA table_info(user_progress)')
print('schema=', cur.fetchall())
conn.close()
