from werkzeug.security import generate_password_hash
from datetime import datetime, timezone
import sqlite3
import sys

try:
    conn = sqlite3.connect('savvy_scout.db')
    conn.execute('DELETE FROM users')
    
    users = [
        ('mark', 'Mark', False),
        ('kanvesh', 'Kanvesh', False),
        ('hammad', 'Hammad', False),
        ('victoria', 'Victoria', True),
    ]
    
    for username, display_name, is_victoria in users:
        conn.execute(
            'INSERT INTO users (username, password_hash, display_name, is_victoria, created_at) VALUES (?, ?, ?, ?, ?)',
            (username, generate_password_hash('password'), display_name, int(is_victoria), datetime.now(timezone.utc).isoformat())
        )
    
    conn.commit()
    conn.close()
    
    print('SUCCESS: Test users created')
    sys.exit(0)
except Exception as e:
    print(f'ERROR: {e}')
    sys.exit(1)
