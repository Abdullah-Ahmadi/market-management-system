# MMS Security Notes — Refined Version

## Application controls implemented

- Authentication and password hashing use Django's authentication framework.
- Mandatory password rules are enforced server-side: minimum length, uppercase, lowercase, number and symbol. A password may resemble the username, but MMS shows a non-blocking warning because that pattern is easier to guess.
- Login/logout and state-changing forms use Django CSRF protection.
- Role and data-scope checks are enforced in Django views/querysets, not only by hidden interface elements.
- Salesmen cannot retrieve another salesman's transaction merely by changing a URL ID.
- Customer type-ahead search is scope-aware and returns only permitted customers.
- Salesman unit prices are enforced on the server. Browser-tampered prices are replaced by the product's correct master price; privileged operational roles may override prices.
- Sale totals are calculated on the server; JavaScript totals are previews only.
- Audit-log application pages are System-Admin-only, and AuditLog records are read-only in Django Admin.
- Transaction corrections/voiding preserve historical records and produce audit events.
- Customer/product/sale identifiers are generated server-side.
- Profile-picture and company-logo uploads have extension and size restrictions. The company-logo setting is available only through System Admin settings.
- The System Administrator role is protected at the model/form level so its core privileges cannot be switched off by ordinary application or Django-admin model saves.
- A System Administrator cannot demote or deactivate their own account through the normal MMS user editor.
- Backup and restore are reserved for System Admin.
- Restorable `.mmsbackup` packages include an integrity checksum; restore validates paths, file count, unpacked size, format version and presence of an active administrator before applying the snapshot.
- Restore creates a pre-restore safety backup and replaces database state inside a transaction; media replacement has its own rollback path.
- Dynamic session timeout is controlled by System Settings.
- Production settings support secure cookies, HSTS, content-type-sniffing protection and frame denial.
- Bootstrap and custom JavaScript are served locally, reducing third-party front-end dependency exposure.

## Backup security

A `.mmsbackup` package contains company operational data and Django password hashes. It is intentionally restorable, so treat the file as sensitive:

- store it only in protected company-controlled storage;
- restrict access to trusted administrators;
- do not email or publicly share it;
- keep more than one recent backup;
- periodically test a restore on a non-production system;
- keep an off-server copy so a server failure does not destroy both the live system and its backups.

The package is integrity-checked but not encrypted by MMS. Use encrypted storage/volume controls when required by company policy.

## Production requirements

- Never deploy with the default development secret key.
- Set `DJANGO_DEBUG=False`.
- Restrict `DJANGO_ALLOWED_HOSTS` to the actual host names.
- Use HTTPS/TLS and enable secure redirect only after HTTPS is configured correctly.
- Change or remove every demo account/password before real use.
- Grant `/admin/` and System Admin credentials only to trusted personnel.
- Review role permissions after organizational changes.
- Use a production database appropriate for expected concurrency and data volume.
- Keep application code and database/media backups on separate failure domains.
- Keep Python, Django, operating system and browser components patched.
- Use a reverse proxy with TLS, request/body limits, logging and appropriate firewall controls.
- Run `python manage.py check --deploy` before production rollout.
- For an internet-facing or business-critical deployment, conduct an independent security review/penetration test and user-acceptance test.

Audit records support accountability but do not replace protected web-server, operating-system, database and infrastructure logs.

## Public GitHub + Neon + Render deployment

- The public repository contains source code only; deployment secrets belong in Render environment variables.
- The hosted application should use Neon PostgreSQL through `DATABASE_URL`, not a committed SQLite database.
- `DJANGO_SECRET_KEY` is mandatory whenever `DJANGO_DEBUG=False`.
- Render's generated hostname is added automatically to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`.
- WhiteNoise serves versioned static assets; user-uploaded media is separate from static assets.
- Render Free has an ephemeral local filesystem, so uploaded logos/profile images are temporary unless persistent storage is added.
- Never deploy real company sales/customer data to a public portfolio instance.
- Never run the predictable `seed_demo --with-demo-data` accounts on the public deployment.
