import sqlite3

conn = sqlite3.connect('savvy_scout.db')

print("=== CURRENT STATE AFTER WORKFLOW CHANGES ===")
print()

# Check statuses
statuses = [
    ('AWAITING_PHASE1_APPROVAL', 'Owner reviews FAILs'),
    ('AWAITING_PHASE2_APPROVAL', 'Passed Phase 1, AI scope read pending'),
    ('ESCALATED_TO_VICTORIA', 'FLAGS/MAYBEs for Victoria'),
    ('APPROVED', 'Victoria approved'),
    ('REJECTED', 'Rejected'),
    ('PARKED', 'Parked'),
    ('MONITOR', 'Monitoring status'),
]

for status, description in statuses:
    count = conn.execute('SELECT COUNT(*) FROM notices WHERE status = ?', (status,)).fetchone()[0]
    print(f'{status:30} {count:5} - {description}')

print()
print("=== PHASE 1 APPROVAL QUEUE (for owner FAILs review) ===")
owners = ['Mark', 'Kanvesh', 'Hammad', None]
for owner in owners:
    if owner is None:
        count = conn.execute('SELECT COUNT(*) FROM notices WHERE status = ? AND owner IS NULL', ('AWAITING_PHASE1_APPROVAL',)).fetchone()[0]
        owner_name = 'Unassigned'
    else:
        count = conn.execute('SELECT COUNT(*) FROM notices WHERE status = ? AND owner = ?', ('AWAITING_PHASE1_APPROVAL', owner)).fetchone()[0]
        owner_name = owner
    print(f'{owner_name:20} {count:5}')

print()
print("=== VERIFYING: Do those FAILs have FAIL outcomes? ===")
fail_count = conn.execute('''
    SELECT COUNT(*) FROM notices n
    WHERE n.status = 'AWAITING_PHASE1_APPROVAL'
    AND EXISTS (
        SELECT 1 FROM triage_runs tr
        WHERE tr.notice_id = n.id
        AND tr.headline_outcome = 'FAIL'
        AND tr.id = (SELECT MAX(id) FROM triage_runs WHERE notice_id = n.id)
    )
''').fetchone()[0]

print(f'Notices with FAIL outcome: {fail_count}')

other_outcome = conn.execute('''
    SELECT tr.headline_outcome, COUNT(*) FROM notices n
    JOIN (
        SELECT notice_id, headline_outcome,
               ROW_NUMBER() OVER (PARTITION BY notice_id ORDER BY id DESC) as rn
        FROM triage_runs
    ) tr ON n.id = tr.notice_id AND tr.rn = 1
    WHERE n.status = 'AWAITING_PHASE1_APPROVAL'
    AND tr.headline_outcome != 'FAIL'
    GROUP BY tr.headline_outcome
''').fetchall()

if other_outcome:
    print("ERROR: Non-FAIL outcomes in Phase 1 approval queue:")
    for outcome, cnt in other_outcome:
        print(f'  {outcome}: {cnt}')
else:
    print("✓ All items in Phase 1 approval queue have FAIL outcomes")

print()
print("=== ESCALATED TO VICTORIA (FLAGS/MAYBEs) ===")
vic_outcomes = conn.execute('''
    SELECT tr.headline_outcome, COUNT(*) FROM notices n
    JOIN (
        SELECT notice_id, headline_outcome,
               ROW_NUMBER() OVER (PARTITION BY notice_id ORDER BY id DESC) as rn
        FROM triage_runs
    ) tr ON n.id = tr.notice_id AND tr.rn = 1
    WHERE n.status = 'ESCALATED_TO_VICTORIA'
    GROUP BY tr.headline_outcome
    ORDER BY tr.headline_outcome
''').fetchall()

for outcome, cnt in vic_outcomes:
    print(f'{outcome}: {cnt}')
