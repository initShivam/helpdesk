import imaplib
import os
from collections.abc import Iterator


class GmailImapClient:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        mailbox: str | None = None,
    ):
        self.host = host or os.getenv("EMAIL_IMAP_HOST", "imap.gmail.com")
        self.port = port or int(os.getenv("EMAIL_IMAP_PORT", "993"))
        self.username = username or os.getenv("EMAIL_IMAP_USERNAME", "")
        self.password = password or os.getenv("EMAIL_IMAP_PASSWORD", "")
        self.mailbox = mailbox or os.getenv("EMAIL_IMAP_MAILBOX", "INBOX")
        self.connection: imaplib.IMAP4_SSL | None = None

    def __enter__(self):
        if not self.username or not self.password:
            raise RuntimeError("EMAIL_IMAP_USERNAME and EMAIL_IMAP_PASSWORD are required")
        self.connection = imaplib.IMAP4_SSL(self.host, self.port)
        self.connection.login(self.username, self.password)
        status, _ = self.connection.select(self.mailbox)
        if status != "OK":
            raise RuntimeError(f"Unable to select IMAP mailbox: {self.mailbox}")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.connection is not None:
            try:
                self.connection.close()
            finally:
                self.connection.logout()

    def unread_messages(self) -> Iterator[tuple[bytes, bytes]]:
        if self.connection is None:
            raise RuntimeError("IMAP client must be used as a context manager")
        status, data = self.connection.uid("search", None, "UNSEEN")
        if status != "OK":
            raise RuntimeError("Unable to search IMAP mailbox")
        for uid in (data[0] or b"").split():
            status, message_data = self.connection.uid("fetch", uid, "(RFC822)")
            if status != "OK":
                raise RuntimeError(f"Unable to fetch IMAP message {uid!r}")
            raw_message = next(
                (part[1] for part in message_data if isinstance(part, tuple)),
                None,
            )
            if raw_message:
                yield uid, raw_message
            else:
                raise RuntimeError(f"IMAP message {uid!r} had no RFC822 payload")

    def mark_seen(self, uid: bytes):
        if self.connection is None:
            raise RuntimeError("IMAP client must be used as a context manager")
        status, _ = self.connection.uid("store", uid, "+FLAGS", r"(\Seen)")
        if status != "OK":
            raise RuntimeError(f"Unable to mark IMAP message {uid!r} as seen")
