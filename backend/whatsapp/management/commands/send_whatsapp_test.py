from django.core.management.base import BaseCommand, CommandError

from whatsapp.services import get_state_instance, send_whatsapp_message, validate_configuration


class Command(BaseCommand):
    help = "Verify GREEN-API instance authorization and optionally send a test message."

    def add_arguments(self, parser):
        parser.add_argument("--phone", help="Indian recipient mobile number.")
        parser.add_argument("--message", help="Test message text.")
        parser.add_argument(
            "--confirm-send",
            action="store_true",
            help="Required to send the supplied message to the real phone number.",
        )

    def handle(self, *args, **options):
        missing = validate_configuration()
        if missing:
            raise CommandError(
                "GREEN-API configuration missing or invalid: " + ", ".join(missing)
            )

        state = get_state_instance()
        self.stdout.write(f"GREEN-API instance status: {state.status}")
        if state.status != "authorized":
            if state.error_code:
                self.stdout.write(f"Error: {state.error_code}")
            return

        if not options["phone"] and not options["message"] and not options["confirm_send"]:
            return
        if not options["phone"] or not options["message"] or not options["confirm_send"]:
            raise CommandError(
                "To send a real test message provide --phone, --message, and --confirm-send."
            )

        result = send_whatsapp_message(options["phone"], options["message"])
        self.stdout.write(f"Test message result: {result.status}")
        if result.message_id:
            self.stdout.write(f"Provider message ID: {result.message_id}")
        if result.error_code:
            self.stdout.write(f"Error: {result.error_code}")
