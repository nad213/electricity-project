import logging
import os
import sys
import threading

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class ConsommationConfig(AppConfig):
    name = 'consommation'

    def ready(self):
        # Skip warm-up during collectstatic, migrate, or test runs.
        # Only warm up when serving via gunicorn or runserver (RUN_MAIN is set by Django's autoreloader).
        command = sys.argv[0] if sys.argv else ''
        subcommand = sys.argv[1] if len(sys.argv) > 1 else ''
        if subcommand in ('collectstatic', 'migrate', 'makemigrations', 'test', 'shell'):
            return
        if 'gunicorn' not in command and not os.environ.get('RUN_MAIN'):
            return

        def _warmup():
            try:
                from . import data_cache
                logger.info("Parquet cache warm-up starting…")
                data_cache.refresh_all(force=False)
                logger.info("Parquet cache warm-up complete.")
            except Exception:
                logger.exception("Parquet cache warm-up failed — will fall back to S3 on first request.")

        thread = threading.Thread(target=_warmup, daemon=True, name="parquet-cache-warmup")
        thread.start()
