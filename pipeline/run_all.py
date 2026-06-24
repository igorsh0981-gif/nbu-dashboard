"""
NBU Dashboard Pipeline Runner
Запускается через GitHub Actions по расписанию.
Аналог Colab ячейки [2] — выполняет полный цикл обновления данных.
"""
import os
import sys
import time
import requests
from datetime import datetime
from pathlib import Path

# ─── КОНФИГУРАЦИЯ ────────────────────────────────────────────────────────────
JIRA_TOKEN  = os.environ['JIRA_TOKEN']
SHEET_ID    = os.environ.get('SHEET_ID', '1zXNvio8ti1tpU4HkuROE9tzzPSQzLBCy_0gxvb7CYR0')
KEY_FILE    = os.environ.get('KEY_FILE', '/tmp/service_account.json')
JIRA_URL    = 'https://jira.partner-app.net'
JIRA_EMAIL  = 'igor.shirykalov@partner-app.net'

# ─── GOOGLE AUTH ─────────────────────────────────────────────────────────────
from google.oauth2.service_account import Credentials
import google.auth.transport.requests

SCOPES = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets',
]

creds = Credentials.from_service_account_file(KEY_FILE, scopes=SCOPES)

def refresh_token():
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token

def http_write(sheet_name, values):
    """Прямая запись в Sheet через REST API (без gspread quota)."""
    token = refresh_token()
    resp = requests.put(
        f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{sheet_name}!A1:ZZ200000',
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        params={'valueInputOption': 'RAW'},
        json={'values': values},
        timeout=60,
    )
    if resp.status_code != 200:
        raise Exception(f"Sheets write error {resp.status_code}: {resp.text[:300]}")
    return resp.json().get('updatedCells', 0)

# Делаем доступными для скриптов
import builtins
builtins._http_write = http_write
builtins.SHEET_ID    = SHEET_ID
builtins.KEY_FILE    = KEY_FILE
builtins.creds       = creds

# Для release_agent (использует _write_sheet)
def _write_sheet(sheet_name, values, _creds, _sheet_id):
    return http_write(sheet_name, values)
builtins._write_sheet = _write_sheet

# ─── PIPELINE ────────────────────────────────────────────────────────────────
total_start = time.time()
here = Path(__file__).parent

print("=" * 55)
print(f"  NBU DASHBOARD UPDATE — {datetime.now().strftime('%d.%m.%Y %H:%M')} (UTC)")
print("=" * 55)

# ── 1. Jira API ───────────────────────────────────────────────
print("\n▶ [1/5] nbu_jira_api.py")
code = (here / 'nbu_jira_api.py').read_text(encoding='utf-8')
code = code.replace("JIRA_TOKEN  = ''", f"JIRA_TOKEN  = '{JIRA_TOKEN}'")
code = code.replace("JIRA_TOKEN = ''",  f"JIRA_TOKEN = '{JIRA_TOKEN}'")
g = {**globals(), **vars(builtins)}
exec(code, g)
# Переносим результаты в глобальный контекст
import pandas as pd
df_csv     = g.get('df_csv', pd.DataFrame())
df_history = g.get('df_history', pd.DataFrame())
print(f"✅ df_csv: {len(df_csv)} задач, история: {len(df_history)} записей")

# ── 2. Normalizer ──────────────────────────────────────────────
print("\n▶ [2/5] nbu_normalizer_v2.py")
g2 = {**g, 'df_csv': df_csv}
exec((here / 'nbu_normalizer_v2.py').read_text(encoding='utf-8'), g2)
headers_norm = g2['headers']
rows_out     = g2['rows_out']
print(f"✅ Нормализовано: {len(rows_out)} строк")

# ── 3. Записываем normalized ──────────────────────────────────
print("\n▶ [3/5] Записываю normalized...")
cells = http_write('normalized', [headers_norm] + rows_out)
print(f"✅ normalized: {cells} ячеек")

# ── 4. Release Agent ──────────────────────────────────────────
print("\n▶ [4/5] nbu_release_agent_v2.py")
import gspread
gc = gspread.authorize(creds)
ss = gc.open_by_key(SHEET_ID)
g3 = {**g2, 'ss': ss, '_write_sheet': _write_sheet, 'creds': creds, 'SHEET_ID': SHEET_ID}
exec((here / 'nbu_release_agent_v2.py').read_text(encoding='utf-8'), g3)
print(f"✅ Release Agent готов")

# ── 5. Team Agent ─────────────────────────────────────────────
print("\n▶ [5/5] nbu_team_agent_v2.py")
g4 = {**g3}
exec((here / 'nbu_team_agent_v2.py').read_text(encoding='utf-8'), g4)
print(f"✅ Team Agent готов")

# ── Итог ──────────────────────────────────────────────────────
elapsed = round(time.time() - total_start, 1)
print(f"\n{'=' * 55}")
print(f"  ГОТОВО за {elapsed}с")
print(f"  normalized:  {len(rows_out)} задач")
print(f"  {datetime.now().strftime('%d.%m.%Y %H:%M')} UTC")
print(f"{'=' * 55}")
