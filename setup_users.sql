DELETE FROM users;
INSERT INTO users (id, username, password_hash, display_name, is_victoria, created_at) VALUES 
(1, 'mark', 'pbkdf2:sha256:600000$xZ7gQ7gJ9Y8K$7f5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e', 'Mark', 0, '2026-07-19T00:00:00+00:00'),
(2, 'kanvesh', 'pbkdf2:sha256:600000$xZ7gQ7gJ9Y8K$7f5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e', 'Kanvesh', 0, '2026-07-19T00:00:00+00:00'),
(3, 'hammad', 'pbkdf2:sha256:600000$xZ7gQ7gJ9Y8K$7f5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e', 'Hammad', 0, '2026-07-19T00:00:00+00:00'),
(4, 'victoria', 'pbkdf2:sha256:600000$xZ7gQ7gJ9Y8K$7f5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e', 'Victoria', 1, '2026-07-19T00:00:00+00:00');
