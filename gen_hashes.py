#!/usr/bin/env python
from werkzeug.security import generate_password_hash

password_hash = generate_password_hash('password')
print(f"Password hash for 'password': {password_hash}")

# Output SQL INSERT statements
print("\nSQL INSERT statements:")
print("DELETE FROM users;")
print(f"INSERT INTO users (username, password_hash, display_name, is_victoria, created_at) VALUES ('mark', '{password_hash}', 'Mark', 0, '2026-07-19T00:00:00+00:00');")
print(f"INSERT INTO users (username, password_hash, display_name, is_victoria, created_at) VALUES ('kanvesh', '{password_hash}', 'Kanvesh', 0, '2026-07-19T00:00:00+00:00');")
print(f"INSERT INTO users (username, password_hash, display_name, is_victoria, created_at) VALUES ('hammad', '{password_hash}', 'Hammad', 0, '2026-07-19T00:00:00+00:00');")
print(f"INSERT INTO users (username, password_hash, display_name, is_victoria, created_at) VALUES ('victoria', '{password_hash}', 'Victoria', 1, '2026-07-19T00:00:00+00:00');")
