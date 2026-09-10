from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.backup import build_backup_bytes


class Command(BaseCommand):
    help = 'Create a restorable .mmsbackup package from the current MMS database and media.'

    def add_arguments(self, parser):
        parser.add_argument('--output', help='Output .mmsbackup path. Defaults to the current directory.')

    def handle(self, *args, **options):
        output = options.get('output')
        if output:
            target = Path(output)
        else:
            stamp = timezone.localtime().strftime('%Y-%m-%d-%H%M')
            target = Path.cwd() / f'mms-{stamp}.mmsbackup'
        if target.suffix.lower() != '.mmsbackup':
            target = target.with_suffix('.mmsbackup')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(build_backup_bytes())
        self.stdout.write(self.style.SUCCESS(f'Backup created: {target.resolve()}'))
