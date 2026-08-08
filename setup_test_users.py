#!/usr/bin/env python
"""Create test users for Savvy Scout dashboard."""

from werkzeug.security import generate_password_hash
from datetime import datetime, timezone
import sqlite3

conn = sqlite3.connect('savvy_scout.db')

users = [
    ('mark', 'Mark', False),
    ('kanvesh', 'Kanvesh', False),
    ('hammad', 'Hammad', False),
    ('victoria', 'Victoria', True),
]

# First, delete existing users to reset
conn.execute('DELETE FROM users')
conn.commit()

for username, display_name, is_victoria in users:
    try:
        conn.execute(
            'INSERT INTO users (username, password_hash, display_name, is_victoria, created_at) VALUES (?, ?, ?, ?, ?)',
            (username, generate_password_hash('password'), display_name, int(is_victoria), datetime.now(timezone.utc).isoformat())
        )
        print(f'✓ Created user {username} ({display_name})')
    except Exception as e:
        print(f'✗ Failed to create {username}: {str(e)}')

conn.commit()
conn.close()
print('\n✓ All test users created successfully!')
print('  Username: mark | Password: password | Role: Sector Owner')
print('  Username: kanvesh | Password: password | Role: Sector Owner')
print('  Username: hammad | Password: password | Role: Sector Owner')
print('  Username: victoria | Password: password | Role: Bid Director')
