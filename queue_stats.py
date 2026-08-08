import sqlite3

conn = sqlite3.connect('savvy_scout.db')

print('=== PHASE 1 QUEUE BY OWNER ===')
rows = conn.execute('''
    SELECT owner, COUNT(*) as cnt 
    FROM notices 
    WHERE status = 'AWAITING_PHASE1_APPROVAL' 
    GROUP BY owner 
    ORDER BY cnt DESC
''').fetchall()

for owner, cnt in rows:
    print(f'{owner}: {cnt}')

print()
print('=== TOTAL STATS ===')
phase1_total = conn.execute('SELECT COUNT(*) FROM notices WHERE status = "AWAITING_PHASE1_APPROVAL"').fetchone()[0]
all_total = conn.execute('SELECT COUNT(*) FROM notices').fetchone()[0]

print(f'Total in Phase 1 Queue: {phase1_total}')
print(f'Total Opportunities in System: {all_total}')

print()
print('=== STATUS BREAKDOWN ===')
status_rows = conn.execute('''
    SELECT status, COUNT(*) as cnt 
    FROM notices 
    GROUP BY status 
    ORDER BY cnt DESC
''').fetchall()

for status, cnt in status_rows:
    print(f'{status}: {cnt}')
