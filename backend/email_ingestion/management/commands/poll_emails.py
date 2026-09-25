import time

from django.core.management.base import BaseCommand, CommandError

from email_ingestion.tasks import fetch_emails


class Command(BaseCommand):
    help = "Fetch support emails without requiring Celery or Redis."

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=300,
            help="Seconds to wait between mailbox checks (default: 300).",
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
                self.stderr.write(self.style.ERROR(f"Email fetch failed: {exc}"))
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Email fetch complete: created={result['created']} "
                        f"skipped={result['skipped']}"
                    )
                )

            if options["once"]:
                return
            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                self.stdout.write("\nEmail polling stopped.")
                return
