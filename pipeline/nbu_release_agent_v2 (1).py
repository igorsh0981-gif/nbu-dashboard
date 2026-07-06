"""
NBU Release Agent v2 — читает лист normalized + jira_versions,
считает статистику по релизам, пишет в лист releases.
"""
from collections import defaultdict
from datetime import datetime

STATUS_CATS = ['backlog', 'todo', 'analytics', 'inprog', 'testing', 'done', 'rejected']
NO_RELEASE  = 'Без релиза'

print("[1/4] Читаю jira_versions...")
JIRA_VERSIONS = {}
try:
    _jv_values = ss.worksheet('jira_versions').get_all_values()
    if len(_jv_values) < 2:
        print(f"      ⚠ Лист jira_versions пуст или содержит только заголовок ({len(_jv_values)} строк)")
    else:
        _jv_headers = [h.strip() for h in _jv_values[0]]
        print(f"      Заголовки jira_versions: {_jv_headers}")
        _idx_release = _jv_headers.index('release') if 'release' in _jv_headers else 0
        _idx_desc    = _jv_headers.index('description') if 'description' in _jv_headers else 1
        _idx_start   = _jv_headers.index('start_date') if 'start_date' in _jv_headers else 2
        _idx_end     = _jv_headers.index('release_date') if 'release_date' in _jv_headers else 3
        _idx_status  = _jv_headers.index('jira_status') if 'jira_status' in _jv_headers else 4
        for row in _jv_values[1:]:
            if len(row) <= _idx_release:
                continue
            rel = str(row[_idx_release]).strip()
            if rel:
                JIRA_VERSIONS[rel] = {
                    'description':  str(row[_idx_desc]).strip() if len(row) > _idx_desc else '',
                    'start_date':   str(row[_idx_start]).strip() if len(row) > _idx_start else '',
                    'release_date': str(row[_idx_end]).strip() if len(row) > _idx_end else '',
                    'jira_status':  str(row[_idx_status]).strip() if len(row) > _idx_status else 'unreleased',
                }
except Exception as e:
    print(f"      ❌ Ошибка чтения jira_versions: {e}")
print(f"      Загружено версий: {len(JIRA_VERSIONS)}")
if len(JIRA_VERSIONS) > 0:
    _sample_key = next(iter(JIRA_VERSIONS))
    print(f"      Пример записи ({_sample_key}): {JIRA_VERSIONS[_sample_key]}")

print("[2/4] Читаю normalized...")
norm_rows = ss.worksheet('normalized').get_all_records(default_blank='')
if not norm_rows:
    raise ValueError("Лист normalized пуст.")
print(f"      Строк: {len(norm_rows)}")

print("[3/4] Считаю статистику по релизам...")
releases = defaultdict(lambda: {
    'total': 0, 'backlog': 0, 'todo': 0, 'analytics': 0,
    'inprog': 0, 'testing': 0, 'done': 0, 'rejected': 0,
    'components': set(), 'due_dates': [],
})

for row in norm_rows:
    release_raw = str(row.get('release', '')).strip()
    rel_list = [r.strip() for r in release_raw.split(',') if r.strip()]
    if not rel_list:
        rel_list = [NO_RELEASE]
    cat  = str(row.get('status_category', '')).strip().lower()
    comp = str(row.get('components', '')).strip()
    due  = str(row.get('due_date', '')).strip()
    for rel in rel_list:
        r = releases[rel]
        r['total'] += 1
        if cat in STATUS_CATS:
            r[cat] += 1
        else:
            r['todo'] += 1
        for c in comp.split(','):
            c = c.strip()
            if c:
                r['components'].add(c)
        if due:
            r['due_dates'].append(due)

for rel_name in JIRA_VERSIONS:
    if rel_name not in releases:
        releases[rel_name]

print(f"      Итого релизов: {len(releases)}")

now = datetime.now().strftime('%Y-%m-%d %H:%M')
output_rows = []

for rel_name, r in sorted(releases.items()):
    total = r['total']
    pct   = round(r['done'] / total * 100, 1) if total > 0 else 0.0
    norm_dates = []
    for d in r['due_dates']:
        d = d.strip()
        if len(d) == 10 and d[4] == '-':
            norm_dates.append(d)
        elif len(d) == 10 and d[2] == '.':
            p = d.split('.')
            if len(p) == 3:
                norm_dates.append(f"{p[2]}-{p[1]}-{p[0]}")
    v = JIRA_VERSIONS.get(rel_name, {})
    output_rows.append([
        rel_name, total,
        r['backlog'], r['todo'], r['analytics'], r['inprog'],
        r['testing'], r['done'], r['rejected'], pct,
        ', '.join(sorted(r['components'])),
        min(norm_dates) if norm_dates else '',
        v.get('start_date', ''),
        v.get('release_date', ''),
        v.get('description', ''),
        v.get('jira_status', 'unreleased'),
        now,
    ])

print("[4/4] Пишу в releases...")
headers = [
    'release', 'total',
    'backlog', 'todo', 'analytics', 'inprog', 'testing', 'done', 'rejected',
    'pct_done', 'components', 'due_date',
    'start_date', 'release_date', 'description', 'jira_status', 'updated_at'
]
cells = _write_sheet('releases', [headers] + output_rows, creds, SHEET_ID)
print(f"✅ Release Agent v2 готов: {len(output_rows)} релизов, {cells} ячеек")
