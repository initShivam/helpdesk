from dataclasses import dataclass, field
from datetime import datetime
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from typing import BinaryIO


@dataclass
class ParsedAttachment:
    filename: str
    content_type: str
    content: bytes


@dataclass
class ParsedEmail:
    message_id: str
    thread_id: str
    sender_email: str
    subject: str
    body: str
    received_at: datetime | None
    attachments: list[ParsedAttachment] = field(default_factory=list)


def _decode_text(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def parse_email(raw_message: bytes | BinaryIO) -> ParsedEmail:
    if hasattr(raw_message, "read"):
        raw_message = raw_message.read()
    message = BytesParser(policy=policy.default).parsebytes(raw_message)

    sender = getaddresses([message.get("From", "")])[0][1].strip().lower()
    if not sender:
        raise ValueError("Inbound email is missing a valid From address")
    message_id = message.get("Message-ID", "").strip()
    if not message_id:
        raise ValueError("Inbound email is missing Message-ID")

    received_at = None
    if message.get("Date"):
        try:
            received_at = parsedate_to_datetime(message["Date"])
        except (TypeError, ValueError, IndexError):
            received_at = None

    bodies: list[str] = []
    attachments: list[ParsedAttachment] = []
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        filename = part.get_filename()
        if filename:
            attachments.append(
                ParsedAttachment(
                    filename=filename,
                    content_type=part.get_content_type(),
                    content=part.get_payload(decode=True) or b"",
                )
            )
        elif part.get_content_type() == "text/plain":
            bodies.append(_decode_text(part))

    references = message.get("References", "").split()
    thread_id = (
        message.get("X-GM-THRID", "").strip()
        or (references[0] if references else "")
        or message.get("In-Reply-To", "").strip()
        or message_id
    )

    return ParsedEmail(
        message_id=message_id,
        thread_id=thread_id,
        sender_email=sender,
        subject=message.get("Subject", "").strip(),
        body="\n\n".join(body for body in bodies if body).strip(),
        received_at=received_at,
        attachments=attachments,
    )
