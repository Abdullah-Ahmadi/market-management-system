# MMS Refined Version 1 — Change Log

This revision keeps the existing MMS logic and adds the requested refinements:

- Added shared **daily zone dispatch serials** in `YYMMDDNN` format (for example Zone A on 10-Sep-2026 = `26091001`, Zone B = `26091002`).
- New sale numbers are now per-zone/per-day, for example `SALE-26091001-00001`, `SALE-26091001-00002`. Existing historical sale numbers are preserved during upgrade.
- Added a management-only **Daily Sales Report** Excel sheet for System Admin, Manager and Sales Clerk users. It follows the supplied operational report concept with Disp#, zone, supervisor, salesman, dynamic product columns, total cases, cash and transaction count.
- Reworked Back navigation into deterministic parent-page navigation; it no longer replays browser history or old filter states.
- Reworked category bar charts into horizontal bars with larger, horizontal labels for easier product-size and salesman-name reading.
- Added an administrator-editable company logo under **Settings → Company & branding**; the built-in wave emblem remains as fallback branding.
- Removed username-similarity as a blocking Django password rule. Similar passwords are now allowed but produce a visible warning.
- Added **Cases / Cash** analysis switching to the Dashboard, Reports & Analytics, and Zone detail analytics.
- Added case-volume calculations to daily, salesman, product, zone, customer and sale-type analysis while preserving cash/value analysis.
- Updated tables to show both cases and cash where useful.
- Rebuilt Excel export around useful analysis rather than only generic transaction data. The workbook now contains Analysis, Daily Trend, Salesmen, Products, Zones, Customers, Sale Mix and Transactions sheets.
- Changed the report export button label from `Excel .xlsx` to `Excel`.
- Protected System Administrator core permissions from accidental reduction and protected an administrator from demoting/deactivating their own account in the standard editor.
- Reserved Backup & Restore for System Admin.
- Replaced the user-facing JSON backup with a restorable `.mmsbackup` recovery package containing application records and uploaded media.
- Added backup integrity validation, automatic pre-restore safety backup, in-app restore, media rollback and database transaction handling.
- Added `python manage.py backup_mms` and `python manage.py restore_mms` for command-line disaster recovery.
- Added migration `0003_refinements.py` for the company logo field and `0004_zone_daily_serials.py` for zone/day serials and sale numbering.
- Expanded automated test coverage and dependency-free package verification for the new behavior.
