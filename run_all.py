"""
NBU Team Agent v2 — читает normalized, считает статистику по исполнителям,
пишет в лист team.
"""
from collections import defaultdict
from datetime import datetime

STATUS_CATS = ['backlog', 'todo', 'analytics', 'inprog', 'testing', 'done', 'rejected']
NO_ASSIGNEE = 'Не назначено'

print("[1/3] Читаю normalized...")
rows = ss.worksheet('normalized').get_all_records(default_blank='')
if not rows:
    raise ValueError("Лист normalized пуст.")
print(f"      Строк: {len(rows)}")

print("[2/3] Считаю статистику по исполнителям...")
team = defaultdict(lambda: {
    'total': 0, 'backlog': 0, 'todo': 0, 'analytics': 0,
    'inprog': 0, 'testing': 0, 'done': 0, 'rejected': 0,
    'releases': set(), 'components': set(),
})

for row in rows:
    assignee = str(row.get('assignee', '')).strip() or NO_ASSIGNEE
    cat      = str(row.get('status_category', '')).strip().lower()
    comp     = str(row.get('components', '')).strip()
    release_raw = str(row.get('release', '')).strip()
    rel_list = [r.strip() for r in release_raw.split(',') if r.strip()]
    m = team[assignee]
    m['total'] += 1
    if cat in STATUS_CATS:
        m[cat] += 1
    else:
        m['todo'] += 1
    for rel in rel_list:
        m['releases'].add(rel)
    for c in comp.split(','):
        c = c.strip()
        if c:
            m['components'].add(c)

print(f"      Уникальных исполнителей: {len(team)}")

now = datetime.now().strftime('%Y-%m-%d %H:%M')
output_rows = []

for assignee in sorted(team.keys(), key=lambda x: (x == NO_ASSIGNEE, x)):
    m     = team[assignee]
    total = m['total']
    pct   = round(m['done'] / total * 100, 1) if total > 0 else 0.0
    output_rows.append([
        assignee, total,
        m['backlog'], m['todo'], m['analytics'], m['inprog'],
        m['testing'], m['done'], m['rejected'], pct,
        ', '.join(sorted(m['releases'])),
        ', '.join(sorted(m['components'])),
        now,
    ])

print("[3/3] Пишу в team...")
headers = [
    'assignee', 'total',
    'backlog', 'todo', 'analytics', 'inprog', 'testing', 'done', 'rejected',
    'pct_done', 'releases', 'components', 'updated_at'
]
cells = _write_sheet('team', [headers] + output_rows, creds, SHEET_ID)
print(f"✅ Team Agent v2 готов: {len(output_rows)} исполнителей, {cells} ячеек")
