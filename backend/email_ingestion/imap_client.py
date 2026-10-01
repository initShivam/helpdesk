import hashlib
import imaplib
import logging
import os
import re

logger = logging.getLogger(__name__)


class GmailImapClient:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        mailbox: str | None = None,
        timeout: int | None = None,
    ):
        self.host = host or os.getenv("EMAIL_IMAP_HOST", "imap.gmail.com")
        self.port = port or int(os.getenv("EMAIL_IMAP_PORT", "993"))
        self.username = username or os.getenv("EMAIL_IMAP_USERNAME", "")
        self.password = password or os.getenv("EMAIL_IMAP_PASSWORD", "")
        self.mailbox = mailbox or os.getenv("EMAIL_IMAP_MAILBOX", "INBOX")
        self.account_fingerprint = hashlib.sha256(
            f"{self.host.lower()}:{self.port}:{self.username.lower()}".encode()
        ).hexdigest()
        self.timeout = timeout or int(os.getenv("EMAIL_IMAP_TIMEOUT", "30"))
        self.connection: imaplib.IMAP4_SSL | None = None
        self.uid_validity: int | None = None
        self.uid_next: int | None = None

    def __enter__(self):
        if not self.username or not self.password:
            raise RuntimeError("EMAIL_IMAP_USERNAME and EMAIL_IMAP_PASSWORD are required")
        logger.info("mailbox_connection_start host=%s port=%s mailbox=%s", self.host, self.port, self.mailbox)
        try:
            self.connection = imaplib.IMAP4_SSL(
                self.host,
                self.port,
                timeout=self.timeout,
            )
            self.connection.login(self.username, self.password)
            status, _ = self.connection.select(self.mailbox)
            if status != "OK":
                raise RuntimeError(f"Unable to select IMAP mailbox: {self.mailbox}")
            status, data = self.connection.status(self.mailbox, "(UIDVALIDITY UIDNEXT)")
            if status != "OK" or not data:
                raise RuntimeError(f"Unable to read IMAP UID state for mailbox: {self.mailbox}")
            status_text = b" ".join(
                item if isinstance(item, bytes) else str(item).encode()
                for item in data
            )
            uid_validity = re.search(rb"UIDVALIDITY\s+(\d+)", status_text, re.IGNORECASE)
            uid_next = re.search(rb"UIDNEXT\s+(\d+)", status_text, re.IGNORECASE)
            if not uid_validity or not uid_next:
                raise RuntimeError(f"IMAP mailbox did not return UIDVALIDITY/UIDNEXT: {self.mailbox}")
            self.uid_validity = int(uid_validity.group(1))
            self.uid_next = int(uid_next.group(1))
            logger.info(
                "mailbox_connection_ready mailbox=%s uid_validity=%s uid_next=%s",
                self.mailbox,
                self.uid_validity,
                self.uid_next,
            )
            return self
        except Exception:
            logger.exception("mailbox_connection_failed host=%s port=%s mailbox=%s", self.host, self.port, self.mailbox)
            if self.connection is not None:
                try:
                    self.connection.logout()
                except Exception:
                    logger.debug("mailbox_connection_cleanup_failed mailbox=%s", self.mailbox, exc_info=True)
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        if self.connection is not None:
            try:
                if self.connection.state == "SELECTED":
                    self.connection.close()
            except Exception:
                # The mailbox work is already complete; a disconnected socket
                # during cleanup must not turn a successful sync into a 502.
                logger.debug("Unable to close IMAP mailbox cleanly", exc_info=True)
            try:
                self.connection.logout()
            except Exception:
                logger.debug("Unable to log out of IMAP cleanly", exc_info=True)

    def search_uids_after(self, last_processed_uid: int) -> list[bytes]:
        if self.connection is None:
            raise RuntimeError("IMAP client must be used as a context manager")
        if self.uid_next is None:
            raise RuntimeError("IMAP UIDNEXT is unavailable")
        first_uid = last_processed_uid + 1
        last_uid = self.uid_next - 1
        if first_uid > last_uid:
            logger.info(
                "mailbox_uid_search mailbox=%s uid_range=%s:%s matched=0",
                self.mailbox,
                first_uid,
                last_uid,
            )
            return []
        status, data = self.connection.uid("search", None, "UID", f"{first_uid}:{last_uid}")
        if status != "OK":
            raise RuntimeError("Unable to search IMAP mailbox")
        uids = sorted((data[0] or b"").split(), key=int)
        logger.info(
            "mailbox_uid_search mailbox=%s uid_range=%s:%s matched=%s",
            self.mailbox,
            first_uid,
            last_uid,
            len(uids),
        )
        return uids

    def fetch_message(self, uid: bytes) -> bytes:
        if self.connection is None:
            raise RuntimeError("IMAP client must be used as a context manager")
        logger.info("mailbox_message_fetch_start mailbox=%s uid=%s", self.mailbox, uid.decode(errors="replace"))
        status, message_data = self.connection.uid("fetch", uid, "(RFC822)")
        if status != "OK":
            raise RuntimeError(f"Unable to fetch IMAP message {uid!r}")
        raw_message = next(
            (part[1] for part in message_data if isinstance(part, tuple)),
            None,
        )
        if not raw_message:
            raise RuntimeError(f"IMAP message {uid!r} had no RFC822 payload")
        return raw_message

    def mark_seen(self, uid: bytes):
        if self.connection is None:
            raise RuntimeError("IMAP client must be used as a context manager")
        status, _ = self.connection.uid("store", uid, "+FLAGS", r"(\Seen)")
        if status != "OK":
            raise RuntimeError(f"Unable to mark IMAP message {uid!r} as seen")
