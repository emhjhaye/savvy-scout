import sqlite3

conn = sqlite3.connect('savvy_scout.db')

print('=== TOP BUYERS IN ESCALATED (1808) ===')
top_buyers = conn.execute('''
    SELECT buyer, COUNT(*) as cnt 
    FROM notices 
    WHERE status = 'ESCALATED_TO_VICTORIA'
    GROUP BY buyer 
    ORDER BY cnt DESC 
    LIMIT 8
''').fetchall()
for buyer, cnt in top_buyers:
    print(f'{buyer}: {cnt}')

print()
print('=== TOP BUYERS IN PHASE 1 UNASSIGNED (845) ===')
unassigned = conn.execute('''
    SELECT buyer, COUNT(*) as cnt 
    FROM notices 
    WHERE status = 'AWAITING_PHASE1_APPROVAL' AND owner IS NULL
    GROUP BY buyer 
    ORDER BY cnt DESC 
    LIMIT 8
''').fetchall()
for buyer, cnt in unassigned:
    print(f'{buyer}: {cnt}')

print()
print('=== TRIFORK CHECK ===')
trifork = conn.execute("SELECT COUNT(*) FROM notices WHERE buyer LIKE '%Trifork%'").fetchone()[0]
total = conn.execute("SELECT COUNT(*) FROM notices").fetchone()[0]
print(f'Triforks: {trifork} out of {total} total ({100*trifork/total:.1f}%)')

print()
print('=== UNIQUE BUYERS ===')
buyers = conn.execute("SELECT COUNT(DISTINCT buyer) FROM notices").fetchone()[0]
print(f'Total unique buyers: {buyers}')

# Sample some buyer names
print()
print('=== SAMPLE BUYERS ===')
samples = conn.execute("SELECT DISTINCT buyer FROM notices LIMIT 15").fetchall()
for (buyer,) in samples:
    print(f'  {buyer}')
