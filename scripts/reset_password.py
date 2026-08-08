"""Reset a user's password in the Savvy Scout SQLite DB.
Usage: python reset_password.py <username> <new_password>
This script does NOT print the password. It only prints success/failure.
"""
import sys
import sqlite3
from werkzeug.security import generate_password_hash

if len(sys.argv) != 3:
    print("Usage: reset_password.py <username> <new_password>")
    sys.exit(2)

username = sys.argv[1]
new_password = sys.argv[2]

db = 'savvy_scout.db'
conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute("SELECT id FROM users WHERE username = ?", (username,))
user = cur.fetchone()
if not user:
    print(f"No such user: {username}")
    conn.close()
    sys.exit(1)

password_hash = generate_password_hash(new_password)
cur.execute("UPDATE users SET password_hash = ? WHERE username = ?", (password_hash, username))
conn.commit()
conn.close()
print(f"Password updated for user '{username}'")
