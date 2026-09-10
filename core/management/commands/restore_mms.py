from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.backup import restore_backup, save_safety_backup


class Command(BaseCommand):
    help = 'Restore MMS business data and media from a .mmsbackup package.'

    def add_arguments(self, parser):
        parser.add_argument('backup_file', help='Path to a .mmsbackup package.')
        parser.add_argument('--yes', action='store_true', help='Confirm destructive restore without an interactive prompt.')

    def handle(self, *args, **options):
        source = Path(options['backup_file'])
        if not source.exists() or not source.is_file():
            raise CommandError(f'Backup file not found: {source}')
        if source.suffix.lower() != '.mmsbackup':
            raise CommandError('Restore requires a .mmsbackup file.')
        if not options['yes']:
            answer = input('This will replace current MMS business data. Type RESTORE to continue: ').strip()
            if answer != 'RESTORE':
                raise CommandError('Restore cancelled.')
        safety = save_safety_backup()
        self.stdout.write(f'Pre-restore safety backup: {safety}')
        try:
            with source.open('rb') as handle:
                result = restore_backup(handle)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Restore complete. Snapshot created at: {result.get('created_at', 'unknown')}"))
