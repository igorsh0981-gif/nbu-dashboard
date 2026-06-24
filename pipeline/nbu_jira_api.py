"""
NBU Jira API Loader v2
Загружает все задачи + историю статусов через Jira REST API.
Пишет листы: normalized (df_csv), status_history, jira_versions

Запуск в Google Colab ПОСЛЕ nbu_config.py:
    exec(open(f'{DRIVE_DIR}/nbu_jira_api.py', encoding='utf-8').read())
"""
import requests
import pandas as pd
import re
import time
from datetime import datetime

# ─── НАСТРОЙКИ ───────────────────────────────────────────────────────────────
JIRA_URL    = 'https://jira.partner-app.net'
JIRA_EMAIL  = 'igor.shirykalov@partner-app.net'
JIRA_TOKEN  = ''  # подставляется снаружи: JIRA_TOKEN = 'xxx'

PROJECT_KEY = 'NBU423'
BATCH       = 100

FIELDS = [
    'summary', 'issuetype', 'status', 'assignee', 'priority',
    'fixVersions', 'components', 'created', 'updated',
    'duedate', 'parent', 'labels', 'project',
]

DONE_STATUSES = {
    'done', 'готово к релизу', 'protocol approved', 'closed', 'resolved'
}
INPROG_STATUSES = {
    'in progress', 'code review', 'business analysis', 'system analysis',
    'architecture agreement', 'grooming', 'design', 'customer agreement',
    'testing', 'ready for testing', 'в работе', 'тестирование'
}

# ─── ПРОВЕРКА ТОКЕНА ─────────────────────────────────────────────────────────
if not JIRA_TOKEN:
    raise ValueError(
        "JIRA_TOKEN не заполнен.\n"
        "Перейди: Jira → Profile → Personal Access Tokens → Create token\n"
        "Вставь токен в переменную JIRA_TOKEN."
    )

headers = {'Accept': 'application/json', 'Authorization': f'Bearer {JIRA_TOKEN}'}

def jira_get(url, params=None):
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

# ─── ЗАГРУЗКА ЗАДАЧ ──────────────────────────────────────────────────────────
print("▶ Загружаю задачи из Jira API...")
all_issues = []
start = 0
while True:
    data = jira_get(
        f'{JIRA_URL}/rest/api/2/search',
        params={
            'jql': f'project = {PROJECT_KEY} ORDER BY created ASC',
            'fields': ','.join(FIELDS),
            'expand': 'changelog',
            'startAt': start,
            'maxResults': BATCH,
        }
    )
    issues = data.get('issues', [])
    all_issues.extend(issues)
    total = data.get('total', 0)
    start += len(issues)
    print(f"  Загружено: {start}/{total}", end='\r')
    if start >= total or not issues:
        break
    time.sleep(0.2)

print(f"\n✅ Загружено задач: {len(all_issues)}")

# ─── НОРМАЛИЗАЦИЯ ВЕРСИЙ ─────────────────────────────────────────────────────
def fix_version(v):
    """2.6.2000 → 2.6.0"""
    return re.sub(r'\.\d{4}$', '.0', v)

# ─── ФОРМИРОВАНИЕ df_csv ─────────────────────────────────────────────────────
print("▶ Формирую df_csv...")
rows = []
history_rows = []

for issue in all_issues:
    f = issue.get('fields', {})
    key = issue.get('key', '')

    # Версии (fixVersions)
    versions_raw = f.get('fixVersions', [])
    versions = [fix_version(v.get('name', '')) for v in versions_raw if v.get('name')]

    # Статус
    status_name = (f.get('status') or {}).get('name', '')
    status_cat_raw = (((f.get('status') or {}).get('statusCategory') or {}).get('name', '')).lower()
    if status_name.lower() in DONE_STATUSES:
        status_cat = 'done'
    elif status_name.lower() in INPROG_STATUSES:
        status_cat = 'inprog'
    elif 'test' in status_name.lower():
        status_cat = 'testing'
    elif status_cat_raw in ('in progress',):
        status_cat = 'inprog'
    elif status_cat_raw in ('done',):
        status_cat = 'done'
    elif status_cat_raw in ('to do',):
        status_cat = 'todo'
    else:
        status_cat = 'backlog'

    # Тип задачи
    issue_type = (f.get('issuetype') or {}).get('name', '')

    # История статусов (changelog)
    changelog = issue.get('changelog', {}).get('histories', [])
    for change in changelog:
        date_str = change.get('created', '')[:10]
        author = (change.get('author') or {}).get('name', '')
        for item in change.get('items', []):
            if item.get('field') == 'status':
                history_rows.append({
                    'key': key,
                    'date': date_str,
                    'author': author,
                    'from_status': (item.get('fromString') or '').lower(),
                    'to_status': (item.get('toString') or '').lower(),
                })

    rows.append({
        'Ключ проблемы': key,
        'Тема': f.get('summary', ''),
        'Тип задачи': issue_type,
        'Статус': status_name,
        'Исполнитель': (f.get('assignee') or {}).get('name', ''),
        'Приоритет': (f.get('priority') or {}).get('name', ''),
        'Исправить в версиях': versions[0] if len(versions) > 0 else '',
        'Исправить в версиях.1': versions[1] if len(versions) > 1 else '',
        'Исправить в версиях.2': versions[2] if len(versions) > 2 else '',
        'Исправить в версиях.3': versions[3] if len(versions) > 3 else '',
        'Компоненты': ', '.join([c.get('name', '') for c in (f.get('components') or [])]),
        'Создано': (f.get('created') or '')[:10],
        'Обновлено': (f.get('updated') or '')[:10],
        'Срок выполнения': f.get('duedate', '') or '',
        'Родительская задача': (f.get('parent') or {}).get('key', ''),
        'Метки': ', '.join(f.get('labels', [])),
        'status_category': status_cat,
    })

df_csv = pd.DataFrame(rows)
print(f"✅ df_csv: {len(df_csv)} строк, {len(df_csv.columns)} колонок")

# ─── STATUS HISTORY → Sheet ───────────────────────────────────────────────────
print("▶ Записываю status_history...")
df_history = pd.DataFrame(history_rows)
if len(df_history) > 0:
    h_vals = [list(df_history.columns)] + [list(r) for r in df_history.itertuples(index=False)]
    _http_write('status_history', h_vals)
    print(f"✅ status_history: {len(df_history)} записей")
else:
    print("⚠ История статусов пуста")

print(f"\n✅ nbu_jira_api.py готов")
print(f"   Задач загружено:  {len(df_csv)}")
print(f"   Из них Эпиков:    {len(df_csv[df_csv['Тип задачи']=='Epic'])}")
print(f"   История статусов: {len(df_history)} переходов")
