"""
Management command: refresh all local Parquet cache files from S3.

Usage:
    python manage.py refresh_data          # only re-downloads changed files
    python manage.py refresh_data --force  # re-downloads all files unconditionally
"""

from django.core.management.base import BaseCommand

from consommation import data_cache


class Command(BaseCommand):
    help = 'Refresh local Parquet cache from S3 (checks ETags, re-downloads only changed files).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-download of all files regardless of ETag.',
        )

    def handle(self, *args, **options):
        force = options['force']
        self.stdout.write(
            self.style.NOTICE(
                f"Refreshing Parquet cache (force={force})…"
            )
        )
        data_cache.refresh_all(force=force)
        self.stdout.write(self.style.SUCCESS("Parquet cache refresh complete."))
