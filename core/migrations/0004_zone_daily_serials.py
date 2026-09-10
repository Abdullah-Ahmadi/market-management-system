from collections import defaultdict

from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def assign_zone_serials(apps, schema_editor):
    Zone = apps.get_model('core', 'Zone')
    ZoneSequence = apps.get_model('core', 'ZoneSequence')
    zones = list(Zone.objects.order_by('code', 'id'))
    if len(zones) > 99:
        raise RuntimeError('MMS daily zone serial format supports at most 99 zones.')
    used = set()
    next_number = 1
    for zone in zones:
        code = (zone.code or '').strip().upper()
        preferred = ord(code) - ord('A') + 1 if len(code) == 1 and 'A' <= code <= 'Z' else None
        if preferred and preferred <= 99 and preferred not in used:
            number = preferred
        else:
            while next_number in used:
                next_number += 1
            number = next_number
        used.add(number)
        next_number = max(next_number, number + 1)
        Zone.objects.filter(pk=zone.pk).update(serial_number=number)
    ZoneSequence.objects.update_or_create(singleton=1, defaults={'value': max(used, default=0)})


def backfill_dispatch_serials(apps, schema_editor):
    Sale = apps.get_model('core', 'Sale')
    User = apps.get_model('core', 'User')
    Zone = apps.get_model('core', 'Zone')
    ZoneSaleSequence = apps.get_model('core', 'ZoneSaleSequence')

    user_zones = dict(User.objects.values_list('id', 'zone_id'))
    zone_serials = dict(Zone.objects.values_list('id', 'serial_number'))
    counters = defaultdict(int)

    for sale in Sale.objects.order_by('transaction_time', 'id'):
        zone_id = user_zones.get(sale.salesman_id)
        zone_number = zone_serials.get(zone_id)
        if not zone_id or not zone_number:
            continue
        try:
            day = timezone.localtime(sale.transaction_time).date()
        except (ValueError, TypeError):
            day = sale.transaction_time.date()
        dispatch = f'{day:%y%m%d}{zone_number:02d}'
        Sale.objects.filter(pk=sale.pk).update(dispatch_serial=dispatch)
        counters[(zone_id, day)] += 1

    ZoneSaleSequence.objects.bulk_create(
        [
            ZoneSaleSequence(zone_id=zone_id, date=day, value=value)
            for (zone_id, day), value in counters.items()
        ],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [('core', '0003_refinements')]

    operations = [
        migrations.CreateModel(
            name='ZoneSequence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('singleton', models.PositiveSmallIntegerField(default=1, editable=False, unique=True)),
                ('value', models.PositiveSmallIntegerField(default=0)),
            ],
        ),
        migrations.AddField(
            model_name='zone',
            name='serial_number',
            field=models.PositiveSmallIntegerField(
                blank=True,
                editable=False,
                help_text='Stable zone number used in the daily dispatch serial (01-99).',
                null=True,
                unique=True,
            ),
        ),
        migrations.RunPython(assign_zone_serials, migrations.RunPython.noop),
        migrations.CreateModel(
            name='ZoneSaleSequence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('value', models.PositiveIntegerField(default=0)),
                ('zone', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='daily_sale_sequences', to='core.zone')),
            ],
            options={'ordering': ['-date', 'zone']},
        ),
        migrations.AddConstraint(
            model_name='zonesalesequence',
            constraint=models.UniqueConstraint(fields=('zone', 'date'), name='unique_zone_sale_sequence_day'),
        ),
        migrations.AddField(
            model_name='sale',
            name='dispatch_serial',
            field=models.CharField(
                blank=True,
                db_index=True,
                editable=False,
                help_text='Shared daily serial for all salesmen in the same zone.',
                max_length=16,
            ),
        ),
        migrations.RunPython(backfill_dispatch_serials, migrations.RunPython.noop),
    ]
