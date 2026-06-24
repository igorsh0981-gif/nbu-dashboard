"""
NBU Normalizer v2 — нормализует данные из Jira API (df_csv) или CSV файла.
Формирует лист `normalized` в Google Sheet.

Запуск в Google Colab ПОСЛЕ nbu_config.py и nbu_jira_api.py:
    exec(open(f'{DRIVE_DIR}/nbu_normalizer_v2.py', encoding='utf-8').read())
"""
import pandas as pd
import re
from datetime import datetime

# ─── ЧТЕНИЕ ДАННЫХ ───────────────────────────────────────────────────────────
if 'df_csv' in dir() and hasattr(df_csv, '__len__') and len(df_csv) > 100:
    print(f"Используем df_csv из памяти: {len(df_csv)} строк (Jira API)")
    df_all = df_csv.copy()
else:
    print(f"Читаем CSV файл: {CSV_FILE}")
    df_all = pd.read_csv(CSV_FILE, low_memory=False)

# Строим словарь эпиков ДО фильтрации (key → summary эпика)
EPIC_NAMES = {}
for _, row in df_all[df_all['Тип задачи'] == 'Epic'].iterrows():
    key_e = str(row.get('Ключ проблемы', '')).strip()
    summ_e = str(row.get('Тема', '')).strip()
    if key_e:
        EPIC_NAMES[key_e] = summ_e
print(f"Эпиков найдено: {len(EPIC_NAMES)}")

df = df_all[df_all['Тип задачи'] != 'Epic'].copy()
print(f"Строк без Epic: {len(df)}")

# ─── КОЛОНКИ ВЕРСИЙ ──────────────────────────────────────────────────────────
ver_cols = [c for c in df.columns if 'Исправить в версиях' in c or 'Fix Version' in c]
print(f"Колонки версий: {ver_cols}")

# ─── НОРМАЛИЗАЦИЯ ВЕРСИЙ ─────────────────────────────────────────────────────
def fix_version(v):
    """Убираем суффикс .2000 (артефакт Jira CSV экспорта): 2.6.2000 → 2.6.0"""
    v = str(v).strip()
    if not v or v == 'nan':
        return ''
    return re.sub(r'\.\d{4}$', '.0', v)

def get_release(row):
    """Собираем все версии из всех колонок fixVersions, возвращаем через запятую."""
    versions = []
    for col in ver_cols:
        v = fix_version(row.get(col, ''))
        if v and v not in versions:
            versions.append(v)
    return ', '.join(versions)

# ─── МАППИНГ СТАТУСОВ ────────────────────────────────────────────────────────
DONE_STATUSES = {
    'done', 'готово к релизу', 'protocol approved', 'closed', 'resolved',
    'готово', 'закрыто'
}
TESTING_STATUSES = {
    'testing', 'ready for testing', 'тестирование', 'готово к тестированию',
    'qa', 'review'
}
INPROG_STATUSES = {
    'in progress', 'code review', 'business analysis', 'system analysis',
    'architecture agreement', 'grooming', 'design', 'customer agreement',
    'в работе', 'разработка', 'аналитика'
}
ANALYTICS_STATUSES = {
    'business analysis', 'system analysis', 'architecture agreement',
    'grooming', 'design', 'аналитика', 'системная аналитика'
}
REJECTED_STATUSES = {
    'rejected', 'cancelled', 'won\'t do', 'wont do', 'отклонено', 'отменено'
}

def map_status(status_raw, status_cat_col=None):
    """Маппинг статуса Jira → категория дашборда."""
    # Если status_category уже есть (из Jira API)
    if status_cat_col and str(status_cat_col).strip().lower() in (
        'done', 'inprog', 'testing', 'analytics', 'backlog', 'todo', 'rejected'
    ):
        return str(status_cat_col).strip().lower()

    s = str(status_raw).strip().lower()
    if s in DONE_STATUSES:
        return 'done'
    if s in REJECTED_STATUSES:
        return 'rejected'
    if s in TESTING_STATUSES:
        return 'testing'
    if s in ANALYTICS_STATUSES:
        return 'analytics'
    if s in INPROG_STATUSES:
        return 'inprog'
    if s in ('backlog', 'бэклог', 'open', 'новый', ''):
        return 'backlog'
    return 'todo'

# ─── ФОРМИРОВАНИЕ СТРОК ──────────────────────────────────────────────────────
print("Нормализую строки...")
rows_out = []
now = datetime.now().strftime('%Y-%m-%d %H:%M')

for _, row in df.iterrows():
    key        = str(row.get('Ключ проблемы', '')).strip()
    summary    = str(row.get('Тема', '')).strip()
    issue_type = str(row.get('Тип задачи', '')).strip()
    status_raw = str(row.get('Статус', '')).strip()
    assignee   = str(row.get('Исполнитель', '')).strip()
    priority   = str(row.get('Приоритет', '')).strip()
    components = str(row.get('Компоненты', '') or row.get('Компонент', '')).strip()
    created    = str(row.get('Создано', '')).strip()
    updated    = str(row.get('Обновлено', '')).strip()
    due_date   = str(row.get('Срок выполнения', '')).strip()
    parent     = str(row.get('Родительская задача', '') or row.get('Родитель', '')).strip()
    labels     = str(row.get('Метки', '')).strip()

    release = get_release(row)

    # status_category: берём из API если есть, иначе маппинг
    sc_col = row.get('status_category', '')
    status_cat = map_status(status_raw, sc_col)

    # Чистим nan
    for v in [assignee, components, due_date, parent, labels, release]:
        if v == 'nan':
            v = ''

    # Epic Link — customfield_10102 ("Ссылка на эпик") — подтверждено для этой Jira
    epic_link_raw = str(row.get('Ссылка на эпик', '') or '').strip()
    if epic_link_raw == 'nan': epic_link_raw = ''

    parent_id = parent if parent and parent != 'nan' else ''

    if epic_link_raw and epic_link_raw in EPIC_NAMES:
        epic_link = epic_link_raw
        epic_name = EPIC_NAMES.get(epic_link_raw, '')
    elif parent_id and parent_id in EPIC_NAMES:
        epic_link = parent_id
        epic_name = EPIC_NAMES.get(parent_id, '')
    else:
        epic_link = ''
        epic_name = ''

    project_key = 'NBU423'
    epic_key    = epic_link  # ключ эпика = parent если это эпик

    rows_out.append([
        key,
        summary,       # title
        issue_type,    # type
        status_raw,    # status
        status_cat,    # status_category
        release,
        assignee if assignee != 'nan' else '',
        priority if priority != 'nan' else '',
        components if components != 'nan' else '',
        created if created != 'nan' else '',
        updated if updated != 'nan' else '',
        due_date if due_date != 'nan' else '',
        parent_id,
        project_key,
        labels if labels != 'nan' else '',
        epic_link,
        epic_name,
        epic_key,
    ])

headers = [
    'key', 'title', 'type', 'status', 'status_category',
    'release', 'assignee', 'priority',
    'components', 'created', 'updated', 'due_date',
    'parent_id', 'project_key', 'labels', 'epic_link', 'epic_name', 'epic_key',
]

# Статистика
no_rel  = sum(1 for r in rows_out if not r[5])  # release = index 5
with_rel = len(rows_out) - no_rel
idx_epic_name = headers.index('epic_name')
print(f"\nПодготовлено: {len(rows_out)} строк")
print(f"Без релиза:   {no_rel}")
print(f"С релизом:    {with_rel}")
print(f"С эпиком:     {sum(1 for r in rows_out if r[idx_epic_name])}")
print(f"Колонок:      {len(headers)}")
print(f"Заголовки:    {headers}")
print(f"Без релиза:   {no_rel}")
print(f"С релизом:    {with_rel}")
print(f"Колонок:      {len(headers)}")

# Проверка тестовых задач
test_keys = ['NBU423-5700', 'NBU423-5701', 'NBU423-5705', 'NBU423-5709']
found = [r for r in rows_out if r[0] in test_keys]
if found:
    print("\nИскомые задачи:")
    for r in found:
        print(f"  {r[0]} | тип={r[2]} | кат={r[4]} | релиз={r[7]} | исполнитель={r[5]}")

print(f"\n✅ nbu_normalizer_v2.py готов: {len(rows_out)} задач")
