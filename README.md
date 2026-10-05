# Market Management System (MMS) — Refined Version 1

A responsive Django sales and market-management web application built with **Django, HTML, CSS, JavaScript and Bootstrap**. Version 1 focuses on market operations and sales recording; inventory/stock and trip/order management remain intentionally outside the current scope.

## Public portfolio deployment

This edition is prepared for the same deployment path used for OMS: **Public GitHub → Neon PostgreSQL → Render**. Production configuration is environment-based, PostgreSQL is supported through `DATABASE_URL`, static files are served with WhiteNoise, and Gunicorn is used as the hosted application server. See [`DEPLOYMENT.md`](DEPLOYMENT.md) for the exact deployment sequence.

**Public-repository rule:** never commit real company/customer data, `.env`, database files, Neon credentials, administrator passwords, uploaded media, `.mmsbackup` archives, or exported business reports.

## What this enhanced build includes

### Interface and usability
- Fully responsive application shell, tables and forms for desktop, tablet and mobile.
- Responsive Django Admin styling as well as the custom MMS admin/management screens.
- Pepsi-inspired electric blue / deep blue / black direction with Cristal-water aqua accents and restrained red highlights.
- System Admin can upload/replace the company logo from **Settings → Company & branding**; the wave emblem remains only as the fallback when no logo is uploaded.
- Local Bootstrap assets: the UI does not require a Bootstrap CDN connection.
- Entire record rows/cards are clickable for direct detail navigation where the user has permission.
- Live filters/search on sales, customers, products, users, zones, audit records and reports; no Filter button is needed for ordinary searching.
- Number formatting with thousands separators and unnecessary trailing decimal zeros removed.
- Role-aware Help Center available from the navigation.
- Back navigation uses predictable parent pages instead of browser-history replay, so old filter states are not revisited.

### Authentication and roles
- Secure login/logout and password change.
- Roles: System Admin, Manager, Sales Clerk, Supervisor and Salesman.
- Password show/hide eye control.
- Live password checklist that turns red/green for length, uppercase, lowercase, number and symbol requirements.
- Passwords that resemble the username are **allowed**, but MMS shows a non-blocking warning because they are easier to guess.
- The mandatory complexity requirements are validated on the Django server.
- Server-side role/scoped authorization; hiding a button is never the only access control.

### Employees and organization
- Employee ID, name, position, username, phone, profile picture, zone and supervisor fields.
- Zones have an assigned supervisor.
- Every zone receives a stable two-digit serial slot. The daily dispatch number is `YYMMDDNN` (for example `26091001` for Zone A on 10-Sep-2026). All salesmen in that zone share the same daily dispatch number.
- Separate detail page for every zone with supervisor, salesmen, customers, recent sales and zone analytics.
- Supervisor/salesman hierarchy validation.
- System Admin can manage roles and expanded global system settings.

### Customers / shopkeepers
- Automatic concurrency-safe customer IDs such as `CUST-A00001`.
- Customer creation, editing, search and detail pages.
- Live customer type-ahead in Record Sale plus a **Browse all customers** option for the user's permitted scope.
- Customer search and browsing are scoped to the records the logged-in user is allowed to use.
- Salesmen select existing assigned customers but cannot create or edit customer records; supervisors, monitors and authorized management users handle customer creation/maintenance.

### Products and pricing
- Automatic product codes such as `PROD-00001`.
- Product name, size, unit, wholesale price and retail price.
- Retail price cannot be lower than wholesale price.
- Product detail page with sales history and performance data.
- Every sale has an explicit **Wholesale / Retail** pricing mode. Salesmen may choose either mode for the transaction.
- MMS loads the matching wholesale or retail master price for every selected product.
- Salesmen cannot type an arbitrary unit price. Their chosen pricing mode is enforced again on the server even if a browser request is tampered with.
- System Admin, Manager, Sales Clerk and Supervisor can override the unit price on a transaction when operationally required.

### Sales
- Registered-customer and General / Walk-in sales.
- Multiple products per sale, positive whole-case quantities, discounts and server-calculated totals.
- Fractional quantities such as 0.5 or 2.25 cases are rejected in both the form and server-side model validation.
- Per-zone/per-day sale numbers such as `SALE-26091001-00001`, `SALE-26091001-00002`; the embedded `26091001` is the zone's shared daily dispatch number.
- The individual five-digit sequence restarts independently for each zone on each day.
- Salesman access limited to own operational data.
- Supervisor access limited to team data.
- Manager/Sales Clerk broader market-operation visibility.
- Salesman edit cutoff (default 7:00 PM) and Supervisor extra correction period (default 24 hours), both managed through settings.
- Submitted, locked, corrected and voided states; financial records are preserved rather than silently deleted.
- Corrections and important actions produce audit records.

### Field monitoring
- Separate **Monitor** role, independent from the salesman/supervisor hierarchy and reporting to a Manager.
- Every monitor has an assigned zone and can work with salesmen/customers in that territory.
- Monitors do not receive sales-record access; their operational workspace is Field Monitoring.
- Daily monitoring reports record the salesman observed, shops visited, customer/shopkeeper comments, company-chiller presence, observations/insights and follow-up requirements.
- Monitors see their own monitoring history/KPIs; their assigned Manager sees the reports of monitors who report to them; System Admin can see all monitoring data.
- Monitoring data can be filtered by date, monitor, salesman and zone and exported to CSV.

### Reporting and analysis
- Date, salesman, zone and sale-type filtering with live updates.
- **Cases / Cash toggle** on the main Dashboard, Reports & Analytics, and Zone analytics pages.
- Cases mode focuses on number of cases sold; Cash mode uses sales value.
- Daily trend, registered-vs-general mix, salesman comparison, product performance and zone performance all use the selected measure.
- Tables keep **both Cases and Cash** visible for practical comparison.
- Category bar charts use horizontal bars and larger horizontal labels so product sizes such as `250 ml`, `300 ml`, and salesman names are easier to read.
- CSV export is retained for compatibility.
- The **Excel** button creates a meaningful analysis workbook with sheets for Analysis, Daily Trend, Salesmen, Products, Zones, Customers, Sale Mix and Transactions.
- For **System Admin, Manager and Sales Clerk** users, Excel also includes a **Daily Sales Report** sheet modeled on the company's operational daily report: Date, Disp#, Zone, Supervisor Name, Salesman, dynamic product case columns, Total Cases, Total Cash and Transactions. On a single-day filter, permitted salesmen are retained even when their sales are zero.
- Excel sheets include cases and cash together, top performers, averages and period KPIs; numeric cells use readable `#,##0.##` formatting.
- Charts are implemented in local JavaScript/Canvas, with no additional chart framework dependency.

### Administration, settings and audit
- Expanded System Settings allow the System Admin to manage company identity, currency, sale cutoff, supervisor correction hours, general-sale policy, salesman discounts, page size, report range, dashboard trend range, customer search limit, session timeout and Help/Support contact information.
- Audit-log UI is accessible **only to the System Admin**.
- Audit records are read-only in Django Admin.
- System Administrator core privileges are protected from accidental reduction; the administrator also cannot demote/deactivate their own account through the normal user editor.
- **Backup & Restore is System-Admin-only.** MMS creates a restorable `.mmsbackup` package rather than exposing a JSON file as the user-facing backup.
- A backup package contains MMS business records plus uploaded media (company logo/profile images) and has an integrity checksum.
- The Restore screen validates the package, creates an automatic pre-restore safety backup, then restores the database snapshot and media.
- Command-line `backup_mms` and `restore_mms` commands are included for recovery when the web interface is unavailable but Django can start.
- Dynamic session timeout follows the administrator's setting.

## Not included yet

The following remain future modules, as requested:
- Inventory / stock management
- Vehicle/warehouse stock movements
- Next-day / trip order management

The current models are structured so those modules can be connected later without replacing the sales core.

## Upgrade note for sale numbering

Migration `0004_zone_daily_serials.py` assigns stable zone serial numbers and backfills each historical sale with its shared dispatch serial. To protect references already in use, **existing historical `sale_number` values are not renamed**. All sales created after the upgrade use the new `SALE-YYMMDDNN-00001` format.

## Requirements

- Python 3.10 or newer
- Django 5.2.x (see `requirements.txt`)
- A modern browser

Bootstrap CSS and JavaScript are bundled locally under `static/vendor/`.

SQLite remains the local-development fallback. The hosted portfolio/UAT deployment is prepared for **Neon PostgreSQL** through the `DATABASE_URL` environment variable.

## Fresh installation — Windows PowerShell

```powershell
cd MMS_Public_Portfolio_Render_Neon
py -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py manage.py migrate
py manage.py seed_demo --with-demo-data
py manage.py runserver
```

Open `http://127.0.0.1:8000/`.

## Fresh installation — macOS/Linux

```bash
cd MMS_Public_Portfolio_Render_Neon
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo --with-demo-data
python manage.py runserver
```

## Local demo login accounts

Running `seed_demo --with-demo-data` creates:

| Username | Role |
|---|---|
| `admin` | System Admin |
| `manager` | Manager |
| `clerk` | Sales Clerk |
| `supervisor` | Supervisor — Zone A |
| `supervisor2` | Supervisor — Zone B |
| `sales1` | Salesman — Zone A |
| `sales2` | Salesman — Zone A |

Demo password for all local demo accounts: `MmsDemo!2026`

**Do not run `seed_demo --with-demo-data` on the public Render deployment.** These predictable accounts are for local development only.

If sample data is not wanted, run `python manage.py seed_demo` without `--with-demo-data`, then create an administrator with `python manage.py createsuperuser` and complete the required configuration.

## Upgrading the earlier MMS package

1. Back up the database and media files first.
2. Replace/update the source files with this enhanced package.
3. Activate the environment and install `requirements.txt`.
4. Run:

```bash
python manage.py migrate
```

Migration `0002_enhanced_mms.py`:
- adds zone supervisors;
- converts the old single product price into both wholesale and retail starting values;
- adds product size and automatic product sequencing;
- adds the expanded System Settings fields.

Migration `0003_refinements.py`:
- adds the administrator-managed company logo field.

Existing zones from the old database may initially have no supervisor because a safe migration cannot guess who should supervise them. After migration, log in as System Admin and assign the correct supervisor to every existing zone before normal operation.

## Tests and validation

After installing Django, run:

```bash
python manage.py check
python manage.py test
python manage.py check --deploy
```

A dependency-free package verifier is also included:

```bash
python verify_package.py
```

See `TEST_REPORT.md` for exactly what was executed in the build environment and what still needs to be executed in a real Django runtime.

## Important routes

- `/` — dashboard
- `/sales/new/` — record sale
- `/sales/` — sales records
- `/customers/` — customers
- `/products/` — products
- `/reports/` — analytics/reports
- `/reports/sales.xlsx` — Excel analysis export (normally used through the report page)
- `/zones/` — zones
- `/team/` — user/team management for permitted roles
- `/help/` — Help Center
- `/audit/` — System Admin audit history only
- `/settings/` — System Admin system settings only
- `/backup/` — System Admin Backup & Restore center
- `/backup/download/` — create/download a restorable `.mmsbackup` package
- `/backup/restore/` — restore a validated MMS backup package
- `/admin/` — Django administrative console


## Backup and disaster recovery

From the web interface, sign in as System Admin and open **Backup & Restore**. Use **Create & Download Backup** to save a `.mmsbackup` file. To recover, open **Restore**, select that file, type `RESTORE`, and submit. MMS validates the package and saves a pre-restore safety copy before changing current data.

For command-line recovery:

```bash
python manage.py backup_mms --output backups/company-snapshot.mmsbackup
python manage.py restore_mms backups/company-snapshot.mmsbackup
```

For non-interactive server recovery, add `--yes` to `restore_mms`. Backup files contain sensitive company data and password hashes, so protect them like database backups. Periodically test restoring a recent backup on a non-production copy of the system.

## Production / hosted configuration

The public portfolio build is configured for Render and Neon. Keep these values in Render's private environment variables, never in GitHub:

```text
DJANGO_SECRET_KEY=<long-random-secret>
DJANGO_DEBUG=False
DATABASE_URL=<private Neon PostgreSQL connection string>
DJANGO_TIME_ZONE=Asia/Kabul
DJANGO_SECURE_SSL_REDIRECT=True
MMS_ADMIN_USERNAME=<private admin username>
MMS_ADMIN_PASSWORD=<private strong password>
```

Render automatically provides `RENDER_EXTERNAL_HOSTNAME`, which MMS adds to Django's host and CSRF configuration. See `DEPLOYMENT.md` for the complete GitHub → Neon → Render procedure.

## Future development path

The intended next phases can add inventory, stock movements, orders, returns, payments/credit, sales targets, routes/visits, approvals and notifications while reusing the existing `Sale`, `SaleItem`, `Customer`, `Product`, `User` and `Zone` models.
