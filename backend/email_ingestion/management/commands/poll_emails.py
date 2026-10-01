import os
import time
import logging

from django.core.management.base import BaseCommand, CommandError

from email_ingestion.tasks import fetch_emails

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Fetch support emails without requiring Celery or Redis."

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=int(os.getenv("EMAIL_POLL_INTERVAL_SECONDS", "60")),
            help="Seconds to wait between mailbox checks (default: 60).",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Fetch once and exit instead of polling continuously.",
        )

    def handle(self, *args, **options):
        interval = options["interval"]
        if interval < 1:
            raise CommandError("--interval must be at least 1 second")

        while True:
            try:
                result = fetch_emails()
            except Exception as exc:
                logger.exception("mailbox_poll_failed error=%s", exc)
            else:
                logger.info(
                    "mailbox_poll_complete matched=%s created=%s skipped=%s errors=%s",
                    result["matched"],
                    result["created"],
                    result["skipped"],
                    result["errors"],
                )

            if options["once"]:
                return
            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                self.stdout.write("\nEmail polling stopped.")
                return
