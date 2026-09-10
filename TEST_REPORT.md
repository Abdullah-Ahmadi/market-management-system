# MMS Refined Application — Validation and Test Report

## What was executed in the build environment

The build environment used to prepare this package does **not** contain Django, and its Python package path cannot reach PyPI. Therefore, Django runtime tests could not be executed here. The package includes a full Django `TestCase` suite, but this report deliberately separates tests that were actually executed from tests that must be run after Django is installed.

The following checks **were executed successfully** on the refined source:

- Python AST/source parsing for the complete project through `verify_package.py`.
- Python byte-code compilation for all Python modules (`python -m compileall`).
- Node.js syntax validation for `static/js/app.js` and `static/js/charts.js`.
- Required project/file structure verification.
- Template marker sanity checks across all application templates.
- Static template-to-route cross-check: literal `{% url %}` references resolve to defined application/auth/admin route names.
- Dependency-free XLSX writer test: generated Excel output is a valid ZIP/OOXML workbook package with the required workbook parts.
- Static review of the new Cases/Cash analytics payloads and switching logic.
- Static review of horizontal bar-chart rendering with larger horizontal labels for product sizes and salesman names.
- Static review of company-logo upload field, media rendering and administrator settings integration.
- Static review that username/password similarity is warning-only while mandatory password-complexity rules remain enforced.
- Static review of protected System Administrator permissions and self-demotion/self-deactivation prevention.
- Static review that Backup & Restore access is System-Admin-only.
- Backup package implementation review for manifest/version/checksum validation, path traversal protection, data/media packaging, session invalidation, database sequence reset, pre-restore safety snapshots and media rollback behavior.
- Static review of meaningful Excel analysis sheets: KPI analysis, management Daily Sales Report matrix, daily trend, salesmen, products, zones, customers, sale mix and transaction detail.
- Static review of the `YYMMDDNN` zone dispatch serial and `SALE-YYMMDDNN-00001` per-zone/per-day sale-number implementation and migration.
- Static review that Back navigation is deterministic parent-page navigation and contains no browser-history replay handler.

Run the bundled dependency-free verifier at any time with:

```bash
python verify_package.py
```

## Django TestCase suite included

The `core/tests/` suite covers, among other items:

- Zone-based automatic customer ID sequencing.
- Stable zone serial assignment and shared daily dispatch serial generation.
- Per-zone/per-day transaction numbering (`SALE-YYMMDDNN-00001`, `00002`, ...).
- Automatic product-code sequencing.
- Retail price not being lower than wholesale price.
- Sale item totals and transaction totals.
- Salesman, Supervisor and Manager visibility/scoping.
- Salesman cutoff and Supervisor correction window.
- Login requirement and direct-object access denial.
- Salesmen being forbidden from product-master management.
- Salesman price-tampering prevention for registered-customer sales.
- Salesman price-tampering prevention for General/Walk-in sales.
- Privileged manager unit-price override.
- Scoped live customer-search API.
- Manager denial/System Admin allowance for audit history.
- Help Center availability.
- Cases/Cash report payload generation.
- Excel endpoint workbook/sheet validation, including the management-only Daily Sales Report matrix and product columns.
- Username-similar passwords being accepted when mandatory validators pass.
- System Administrator role invariants preventing core privilege reduction.
- Administrator self-edit protection against demotion/deactivation.
- System-Admin-only backup access.
- `.mmsbackup` creation and restore round-trip behavior, including deletion of post-backup data after restoration.

## Required runtime validation after installing Django

In the extracted project directory run:

```bash
python -m pip install -r requirements.txt
python manage.py check
python manage.py migrate
python manage.py test
python manage.py check --deploy
```

`check --deploy` is useful for reviewing production security settings, but some warnings are expected while running with development defaults such as `DEBUG=True` or an unset production HTTPS configuration.

For an upgrade from an earlier MMS build, first make a copy of the real database and media directory and run the migration/test workflow on that copy before modifying production data.

## Manual acceptance tests recommended before deployment

Use each application role and verify:

1. Desktop, tablet and phone navigation, especially administrator pages and responsive tables/forms.
2. Administrator uploads/replaces the company logo and it renders correctly in login/sidebar branding.
3. Horizontal bar-chart labels remain fully readable for sizes such as 250 ml, 300 ml, longer product descriptions and salesman names on common screen widths.
4. Customer type-ahead works smoothly with hundreds/thousands of test customers.
5. Salesmen cannot edit unit price, including by browser developer tools/request tampering.
6. Manager/Clerk/Supervisor/Admin can override transaction unit price where allowed.
7. Registered-customer sales use wholesale standard price and General/Walk-in sales use retail standard price.
8. Live filters update without a Filter button and row clicks open the expected detail record.
9. Cases/Cash toggle changes KPI cards, charts and rankings to the correct measure on Dashboard, Reports and Zone pages.
10. Excel export opens in the company's actual Microsoft Excel version; for Admin/Manager/Clerk verify the Daily Sales Report sheet matches the selected day, repeats one Disp# for all salesmen in a zone, and reconciles product case totals to Transactions/Products sheets.
11. Manager cannot open `/audit/`, backup pages or direct audit-detail URLs.
12. Password eye/checklist UX works; a username-similar password produces a warning but can be saved if all required rules pass.
13. Protected System Administrator privileges cannot be removed and the current administrator cannot deactivate/demote themself through normal account editing.
14. Sale locking/correction/void behavior is correct at and after the configured cutoff.
15. Create an `.mmsbackup`, add/edit known test data and uploaded media, restore the backup, then verify records/media return to the snapshot state and prior sessions are invalidated.
16. Test command-line recovery using `backup_mms` and `restore_mms` on a non-production copy.

No source package alone should be treated as production-approved until the runtime test suite, user acceptance testing, backup/restore rehearsal and deployment security review are completed in the target environment.

## Standard Back navigation
- Verified the authenticated shell renders a Back action on mapped non-Dashboard pages.
- Verified the Back action is a normal deterministic link to the logical parent page and does not call `window.history.back()`.
- Verified the mobile layout keeps the compact arrow presentation.

## Public deployment preparation — GitHub + Neon + Render

Additional dependency-free checks were run for the public portfolio deployment package:

- All Python source files parsed successfully.
- `render.yaml` parsed successfully as YAML and contains the expected Python web-service, build/start commands, and required secret placeholders.
- No local `.env` or SQLite database is included.
- No uploaded media files are included; only `media/.gitkeep` is tracked.
- A text scan found no live PostgreSQL/Neon connection string in the source package.
- A temporary Git staging test confirmed that protected patterns (`.env`, SQLite database files, `.mmsbackup`, uploaded media) are excluded by `.gitignore`.
- `build.sh` and `start.sh` are included; Render is configured to invoke them through `bash` so deployment does not depend on executable-bit preservation when the repository is prepared from Windows.
- Production settings support `DATABASE_URL`, Render's `RENDER_EXTERNAL_HOSTNAME`, CSRF trusted origins, WhiteNoise static-file serving, proxy HTTPS detection, and mandatory production `DJANGO_SECRET_KEY`.
- The deployment startup creates only missing baseline roles/settings and the first administrator; it does not load predictable demo accounts and does not overwrite later role customization.

Django, Gunicorn, WhiteNoise, dj-database-url and psycopg are not installed in this isolated build environment, so the full hosted/runtime checks must still run after dependencies are installed. On Render, the first deploy itself will exercise dependency installation, `collectstatic`, migrations and Gunicorn startup. After deployment, run the application-level UAT scenarios described in `DEPLOYMENT.md`.
