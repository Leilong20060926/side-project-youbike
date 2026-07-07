import sqlite3

conn = sqlite3.connect('user_progress.db')
cur = conn.cursor()
cur.execute('SELECT sub, email, progress FROM user_progress')
rows = cur.fetchall()
print('rows_count=', len(rows))
for sub, email, progress in rows:
    print('sub=', sub, 'email=', email, 'progress=', progress)
conn.close()
