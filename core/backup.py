"""Restorable MMS backup packages.

A .mmsbackup file is a ZIP container owned by MMS.  Users never need to edit
its internal representation: the Backup & Restore screen creates and restores
it as one unit.  The package includes core business/application records and
files from MEDIA_ROOT (profile pictures and company branding).
"""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.management.color import no_style
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.utils import timezone

from .models import (
    AuditLog,
    Customer,
    MonitorReport,
    MonitorVisit,
    Product,
    ProductSequence,
    Role,
    Sale,
    SaleItem,
    SaleSequence,
    SystemSetting,
    User,
    Zone,
    ZoneSaleSequence,
    ZoneSequence,
)

FORMAT = 'MMS-BACKUP'
FORMAT_VERSION = 1
MAX_ARCHIVE_MEMBERS = 5000
MAX_UNPACKED_BYTES = 500 * 1024 * 1024

BACKUP_MODELS = [
    ('roles', Role),
    ('zone_sequences', ZoneSequence),
    ('zones', Zone),
    ('users', User),
    ('customers', Customer),
    ('monitor_reports', MonitorReport),
    ('monitor_visits', MonitorVisit),
    ('product_sequences', ProductSequence),
    ('products', Product),
    ('sale_sequences', SaleSequence),
    ('zone_sale_sequences', ZoneSaleSequence),
    ('sales', Sale),
    ('sale_items', SaleItem),
    ('settings', SystemSetting),
    ('audit_logs', AuditLog),
]


def _json_bytes(value) -> bytes:
    return json.dumps(value, cls=DjangoJSONEncoder, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def _rows(model):
    return list(model.objects.all().values())


def _safe_media_files():
    root = Path(settings.MEDIA_ROOT)
    if not root.exists():
        return []
    files = []
    for path in root.rglob('*'):
        if path.is_file() and path.name != '.gitkeep':
            files.append((path, path.relative_to(root).as_posix()))
    return files


def build_backup_bytes() -> bytes:
    payload = {
        'schema_version': FORMAT_VERSION,
        'tables': {key: _rows(model) for key, model in BACKUP_MODELS},
    }
    data_bytes = _json_bytes(payload)
    manifest = {
        'format': FORMAT,
        'format_version': FORMAT_VERSION,
        'created_at': timezone.now().isoformat(),
        'data_sha256': hashlib.sha256(data_bytes).hexdigest(),
        'record_counts': {key: len(payload['tables'][key]) for key, _ in BACKUP_MODELS},
        'includes_media': True,
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr('manifest.json', _json_bytes(manifest))
        archive.writestr('data.json', data_bytes)
        for path, relative in _safe_media_files():
            archive.write(path, f'media/{relative}')
    return buffer.getvalue()


def save_safety_backup(directory: Path | None = None) -> Path:
    directory = directory or (Path(settings.BASE_DIR) / 'backups')
    directory.mkdir(parents=True, exist_ok=True)
    stamp = timezone.localtime().strftime('%Y%m%d-%H%M%S')
    target = directory / f'pre-restore-{stamp}.mmsbackup'
    target.write_bytes(build_backup_bytes())
    return target


def _is_safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return not path.is_absolute() and '..' not in path.parts


def _validate_archive(archive: zipfile.ZipFile):
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_MEMBERS:
        raise ValueError('Backup contains too many files.')
    unpacked = sum(info.file_size for info in infos)
    if unpacked > MAX_UNPACKED_BYTES:
        raise ValueError('Backup is too large when unpacked.')
    for info in infos:
        if not _is_safe_member(info.filename):
            raise ValueError('Backup contains an unsafe file path.')
    names = {info.filename for info in infos}
    if 'manifest.json' not in names or 'data.json' not in names:
        raise ValueError('This is not a complete MMS backup package.')


def inspect_backup(uploaded_file):
    uploaded_file.seek(0)
    try:
        with zipfile.ZipFile(uploaded_file, 'r') as archive:
            _validate_archive(archive)
            manifest = json.loads(archive.read('manifest.json'))
            data_bytes = archive.read('data.json')
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
        raise ValueError('The selected file is not a valid MMS backup.') from exc
    finally:
        uploaded_file.seek(0)

    if manifest.get('format') != FORMAT or manifest.get('format_version') != FORMAT_VERSION:
        raise ValueError('This backup format is not supported by this MMS version.')
    actual = hashlib.sha256(data_bytes).hexdigest()
    if actual != manifest.get('data_sha256'):
        raise ValueError('Backup integrity check failed. The file may be damaged or modified.')
    try:
        payload = json.loads(data_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError('Backup data is damaged.') from exc
    if payload.get('schema_version') != FORMAT_VERSION or not isinstance(payload.get('tables'), dict):
        raise ValueError('Backup data structure is not supported.')
    optional_keys = {'zone_sequences', 'zone_sale_sequences', 'monitor_reports', 'monitor_visits'}
    for key, _ in BACKUP_MODELS:
        if key in optional_keys:
            continue
        if key not in payload['tables'] or not isinstance(payload['tables'][key], list):
            raise ValueError(f'Backup is missing required data: {key}.')

    # Prevent restoring a snapshot that would leave the application without an administrator.
    role_codes = {row.get('id'): row.get('code') for row in payload['tables']['roles']}
    has_admin = any(
        row.get('is_active', True)
        and (row.get('is_superuser') or role_codes.get(row.get('role_id')) == Role.ADMIN)
        for row in payload['tables']['users']
    )
    if not has_admin:
        raise ValueError('Backup has no active System Administrator account and cannot be restored.')
    return manifest, payload


def _coerce_row(model, row: dict):
    result = {}
    concrete = {field.attname: field for field in model._meta.concrete_fields}
    for key, value in row.items():
        field = concrete.get(key)
        if not field:
            continue
        if value is None:
            result[key] = None
        else:
            result[key] = field.to_python(value)
    return result


def _bulk_restore(model, rows):
    if not rows:
        return
    objects = [model(**_coerce_row(model, row)) for row in rows]
    model.objects.bulk_create(objects, batch_size=500)


def _repair_zone_serial_state():
    """Rebuild internal serial counters, including when restoring an older backup."""
    zones = list(Zone.objects.order_by('code', 'id'))
    used = {z.serial_number for z in zones if z.serial_number}
    next_number = 1
    for zone in zones:
        if zone.serial_number:
            continue
        while next_number in used:
            next_number += 1
        if next_number > 99:
            raise ValueError('Backup contains more zones than the two-digit serial format supports.')
        Zone.objects.filter(pk=zone.pk).update(serial_number=next_number)
        used.add(next_number)
        next_number += 1
    ZoneSequence.objects.update_or_create(singleton=1, defaults={'value': max(used, default=0)})

    if not ZoneSaleSequence.objects.exists():
        counts = {}
        zone_numbers = dict(Zone.objects.values_list('id', 'serial_number'))
        user_zones = dict(User.objects.values_list('id', 'zone_id'))
        for sale in Sale.objects.order_by('transaction_time', 'id'):
            zone_id = user_zones.get(sale.salesman_id)
            if not zone_id:
                continue
            day = timezone.localtime(sale.transaction_time).date()
            key = (zone_id, day)
            counts[key] = counts.get(key, 0) + 1
            if not sale.dispatch_serial and zone_numbers.get(zone_id):
                Sale.objects.filter(pk=sale.pk).update(
                    dispatch_serial=f'{day:%y%m%d}{zone_numbers[zone_id]:02d}'
                )
        ZoneSaleSequence.objects.bulk_create([
            ZoneSaleSequence(zone_id=zone_id, date=day, value=value)
            for (zone_id, day), value in counts.items()
        ])


def _replace_database(payload):
    tables = payload['tables']

    # Delete in dependency-safe order. Zone.supervisor creates a deliberate Zone/User cycle.
    AuditLog.objects.all().delete()
    MonitorVisit.objects.all().delete()
    MonitorReport.objects.all().delete()
    SaleItem.objects.all().delete()
    Sale.objects.all().delete()
    ZoneSaleSequence.objects.all().delete()
    Customer.objects.all().delete()
    Zone.objects.update(supervisor=None)
    User.objects.all().delete()
    Zone.objects.all().delete()
    Product.objects.all().delete()
    ProductSequence.objects.all().delete()
    SaleSequence.objects.all().delete()
    ZoneSequence.objects.all().delete()
    SystemSetting.objects.all().delete()
    Role.objects.all().delete()

    _bulk_restore(Role, tables['roles'])
    _bulk_restore(ZoneSequence, tables.get('zone_sequences', []))
    Role.objects.get_or_create(
        code=Role.MONITOR,
        defaults={
            'name': 'Monitor',
            'level': 40,
            'can_manage_users': False,
            'can_manage_market_data': False,
            'can_view_all_sales': False,
            'can_export': False,
            'can_backup': False,
            'can_edit_locked_sales': False,
        },
    )
    Role.objects.filter(code=Role.ADMIN).update(
        level=100,
        can_manage_users=True,
        can_manage_market_data=True,
        can_view_all_sales=True,
        can_export=True,
        can_backup=True,
        can_edit_locked_sales=True,
    )

    zone_supervisors = {}
    zone_rows = []
    for row in tables['zones']:
        copy = dict(row)
        zone_supervisors[copy.get('id')] = copy.get('supervisor_id')
        copy['supervisor_id'] = None
        zone_rows.append(copy)
    _bulk_restore(Zone, zone_rows)

    user_supervisors = {}
    user_managers = {}
    user_rows = []
    for row in tables['users']:
        copy = dict(row)
        user_supervisors[copy.get('id')] = copy.get('supervisor_id')
        user_managers[copy.get('id')] = copy.get('manager_id')
        copy['supervisor_id'] = None
        copy['manager_id'] = None
        user_rows.append(copy)
    _bulk_restore(User, user_rows)

    for user_id, supervisor_id in user_supervisors.items():
        if supervisor_id:
            User.objects.filter(pk=user_id).update(supervisor_id=supervisor_id)
    for user_id, manager_id in user_managers.items():
        if manager_id:
            User.objects.filter(pk=user_id).update(manager_id=manager_id)
    for zone_id, supervisor_id in zone_supervisors.items():
        if supervisor_id:
            Zone.objects.filter(pk=zone_id).update(supervisor_id=supervisor_id)

    _bulk_restore(ProductSequence, tables['product_sequences'])
    _bulk_restore(Product, tables['products'])
    _bulk_restore(SaleSequence, tables['sale_sequences'])
    _bulk_restore(ZoneSaleSequence, tables.get('zone_sale_sequences', []))
    _bulk_restore(Customer, tables['customers'])
    _bulk_restore(MonitorReport, tables.get('monitor_reports', []))
    _bulk_restore(MonitorVisit, tables.get('monitor_visits', []))
    _bulk_restore(Sale, tables['sales'])
    _bulk_restore(SaleItem, tables['sale_items'])
    _repair_zone_serial_state()
    _bulk_restore(SystemSetting, tables['settings'])
    _bulk_restore(AuditLog, tables['audit_logs'])
    SystemSetting.get_solo()

    # Sessions are intentionally not part of a backup. Invalidate every existing
    # browser session so a pre-restore session can never inherit another user's ID.
    Session.objects.all().delete()

    # Keep database auto-increment sequences ahead of restored explicit primary keys.
    models = [model for _, model in BACKUP_MODELS]
    sequence_sql = connection.ops.sequence_reset_sql(no_style(), models)
    if sequence_sql:
        with connection.cursor() as cursor:
            for sql in sequence_sql:
                cursor.execute(sql)


def _stage_media(archive: zipfile.ZipFile, temp_root: Path) -> Path:
    staged = temp_root / 'media'
    staged.mkdir(parents=True, exist_ok=True)
    for info in archive.infolist():
        if not info.filename.startswith('media/') or info.is_dir():
            continue
        relative = PurePosixPath(info.filename).relative_to('media')
        target = staged.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info, 'r') as src, target.open('wb') as dst:
            shutil.copyfileobj(src, dst)
    return staged


def _replace_media(staged: Path):
    media_root = Path(settings.MEDIA_ROOT)
    rollback_parent = Path(tempfile.mkdtemp(prefix='mms-media-rollback-'))
    rollback = rollback_parent / 'media'
    try:
        if media_root.exists():
            shutil.copytree(media_root, rollback)
            shutil.rmtree(media_root)
        shutil.copytree(staged, media_root)
        (media_root / '.gitkeep').touch(exist_ok=True)
    except Exception:
        if media_root.exists():
            shutil.rmtree(media_root, ignore_errors=True)
        if rollback.exists():
            shutil.copytree(rollback, media_root)
        raise
    finally:
        shutil.rmtree(rollback_parent, ignore_errors=True)


def restore_backup(uploaded_file):
    manifest, payload = inspect_backup(uploaded_file)
    uploaded_file.seek(0)
    with tempfile.TemporaryDirectory(prefix='mms-restore-') as tmp:
        temp_root = Path(tmp)
        with zipfile.ZipFile(uploaded_file, 'r') as archive:
            _validate_archive(archive)
            staged_media = _stage_media(archive, temp_root)

        with transaction.atomic():
            _replace_database(payload)
            # Filesystem replacement has its own rollback. If it fails, the database
            # transaction is also rolled back because this call remains inside atomic().
            _replace_media(staged_media)

    return {
        'created_at': manifest.get('created_at'),
        'record_counts': manifest.get('record_counts', {}),
    }
