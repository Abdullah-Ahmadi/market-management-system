"""Dependency-free package checks. Run with: python verify_package.py"""
from pathlib import Path
import ast
import re
import subprocess
from io import BytesIO
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent
required = [
    'manage.py', 'mms/settings.py', 'mms/urls.py',
    'core/models.py', 'core/views.py', 'core/forms.py', 'core/permissions.py',
    'core/services.py', 'core/backup.py', 'core/excel.py',
    'core/migrations/0001_initial.py', 'core/migrations/0002_enhanced_mms.py',
    'core/migrations/0003_refinements.py', 'core/migrations/0004_zone_daily_serials.py',
    'templates/base.html', 'templates/_brand.html', 'templates/core/dashboard.html',
    'templates/core/reports.html', 'templates/core/backup.html',
    'templates/core/backup_restore.html', 'templates/core/sale_form.html',
    'static/css/app.css', 'static/js/app.js', 'static/js/charts.js',
    'requirements.txt', 'README.md', 'SECURITY.md', 'TEST_REPORT.md',
]
missing = [p for p in required if not (ROOT / p).exists()]
if missing:
    raise SystemExit('Missing files: ' + ', '.join(missing))

py_files = list(ROOT.rglob('*.py'))
for p in py_files:
    ast.parse(p.read_text(encoding='utf-8'), filename=str(p))
print(f'[OK] Parsed {len(py_files)} Python files.')

for rel in ['static/js/app.js', 'static/js/charts.js']:
    js = ROOT / rel
    try:
        result = subprocess.run(['node', '--check', str(js)], capture_output=True, text=True)
        if result.returncode:
            raise SystemExit(result.stderr)
        print(f'[OK] JavaScript syntax: {rel}')
    except FileNotFoundError:
        print(f'[SKIP] Node.js not installed; JavaScript check skipped for {rel}.')

html_files = list(ROOT.rglob('*.html'))
for p in html_files:
    text = p.read_text(encoding='utf-8')
    if text.count('{%') != text.count('%}'):
        raise SystemExit(f'Unbalanced Django tag markers in {p}')
    if text.count('{{') != text.count('}}'):
        raise SystemExit(f'Unbalanced Django variable markers in {p}')
print(f'[OK] Basic marker check for {len(html_files)} templates.')

# Check named URL references that belong to this project. admin:index is provided by Django.
url_names = {'admin:index'}
for rel in ['core/urls.py', 'mms/urls.py']:
    url_names.update(re.findall(r"name=['\"]([^'\"]+)['\"]", (ROOT / rel).read_text()))
refs = []
for p in html_files:
    refs.extend(re.findall(r"\{\%\s*url\s+['\"]([^'\"]+)['\"]", p.read_text()))
missing_urls = sorted({name for name in refs if name not in url_names})
if missing_urls:
    raise SystemExit('Unknown template URL names: ' + ', '.join(missing_urls))
print(f'[OK] Resolved {len(refs)} template URL references by name.')

# Requested refinement markers.
models_text = (ROOT / 'core/models.py').read_text(encoding='utf-8')
views_text = (ROOT / 'core/views.py').read_text(encoding='utf-8')
base_text = (ROOT / 'templates/base.html').read_text(encoding='utf-8')
app_js = (ROOT / 'static/js/app.js').read_text(encoding='utf-8')
charts_js = (ROOT / 'static/js/charts.js').read_text(encoding='utf-8')
if "self.sale_number = f'SALE-{dispatch}-{seq.value:05d}'" not in models_text or 'dispatch_serial' not in models_text:
    raise SystemExit('Zone/day sale numbering markers are missing.')
if "'Daily Sales Report'" not in views_text or "'Disp#'" not in views_text:
    raise SystemExit('Daily Sales Report export markers are missing.')
if 'data-smart-back' in base_text or 'window.history.back()' in app_js:
    raise SystemExit('Back navigation still contains browser-history behavior.')
if 'Horizontal bars keep product sizes' not in charts_js:
    raise SystemExit('Readable horizontal bar-chart implementation marker is missing.')
print('[OK] Requested serial/report/back/chart refinement markers passed.')

# The XLSX writer is dependency-free, so validate its ZIP/XML package now.
from core.excel import build_xlsx
sample = build_xlsx([
    ('Analysis', [['Metric', 'Value'], ['Cases', 123], ['Cash', 4567.89]]),
    ('Daily Sales Report', [['Date', 'Disp#', 'Zone', 'Supervisor', 'Salesman'] + [f'Product {i}' for i in range(1, 25)] + ['Total Cases', 'Total Cash', 'Transactions'], ['2026-09-10', '26091001', 'A', 'Supervisor', 'Salesman'] + list(range(1, 25)) + [300, 12000, 5]]),
])
with ZipFile(BytesIO(sample)) as book:
    if book.testzip() is not None:
        raise SystemExit('Generated XLSX failed ZIP integrity check.')
    for member in ['xl/workbook.xml', 'xl/worksheets/sheet1.xml', 'xl/worksheets/sheet2.xml']:
        if member not in book.namelist():
            raise SystemExit(f'Generated XLSX missing {member}.')
print('[OK] XLSX writer package integrity passed.')

print('[OK] Package structure verification passed.')
print('Install requirements, then run: python manage.py check && python manage.py test')
