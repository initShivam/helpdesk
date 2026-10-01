import logging
import imaplib
import time

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .tasks import fetch_emails

logger = logging.getLogger(__name__)


class SyncMailboxView(APIView):
    """Fetch new support emails immediately for an authenticated agent."""

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        result = None
        for attempt in range(2):
            try:
                result = fetch_emails()
                break
            except (OSError, imaplib.IMAP4.abort) as exc:
                if attempt == 0:
                    logger.warning("Temporary mailbox connection failure; retrying: %s", exc)
                    time.sleep(1)
                    continue
                logger.exception("Manual support mailbox refresh failed")
                return Response(
                    {
                        "matched": 0,
                        "created": 0,
                        "skipped": 0,
                        "errors": 1,
                        "detail": "Unable to check the support mailbox. Please try again.",
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            except Exception:
                logger.exception("Manual support mailbox refresh failed")
                return Response(
                    {
                        "matched": 0,
                        "created": 0,
                        "skipped": 0,
                        "errors": 1,
                        "detail": "Unable to check the support mailbox. Please try again.",
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )
        return Response(result)
