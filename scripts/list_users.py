import sqlite3

conn=sqlite3.connect('savvy_scout.db')
cur=conn.cursor()
try:
    cur.execute("SELECT username,display_name,is_victoria,created_at FROM users")
    rows=cur.fetchall()
    if not rows:
        print('NO_USERS')
    else:
        for r in rows:
            print('|'.join([str(x) for x in r]))
finally:
    conn.close()
