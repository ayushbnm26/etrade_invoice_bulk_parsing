from __future__ import annotations

from dataclasses import dataclass, field
from email.message import EmailMessage
import mimetypes
from pathlib import Path
import smtplib
import ssl
from typing import Sequence

from invoice_processing.exceptions import EmailDeliveryError


@dataclass(frozen=True)
class SMTPConfig:
    host: str
    port: int
    username: str
    app_password: str = field(repr=False)
    from_email: str


@dataclass(frozen=True)
class EmailAttachment:
    filename: str
    content: bytes = field(repr=False)
    mime_type: str | None = None


def build_email_message(
    smtp_config: SMTPConfig,
    recipient: str,
    subject: str,
    body: str,
    *,
    attachment_paths: Sequence[Path] | None = None,
    attachments: Sequence[EmailAttachment] | None = None,
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = smtp_config.from_email
    message["To"] = recipient
    message["Subject"] = _safe_header(subject)
    message.set_content(body)

    for path in attachment_paths or ():
        _add_attachment(message, _attachment_from_path(path))

    for attachment in attachments or ():
        _add_attachment(message, attachment)

    return message


def send_email(
    smtp_config: SMTPConfig,
    recipient: str,
    subject: str,
    body: str,
    *,
    attachment_paths: Sequence[Path] | None = None,
    attachments: Sequence[EmailAttachment] | None = None,
    timeout: float = 30.0,
) -> None:
    try:
        message = build_email_message(
            smtp_config,
            recipient,
            subject,
            body,
            attachment_paths=attachment_paths,
            attachments=attachments,
        )
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_config.host, smtp_config.port, timeout=timeout) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login(smtp_config.username, smtp_config.app_password)
            smtp.send_message(message)
    except Exception as exc:
        safe_error = sanitize_email_exception(exc, smtp_config)
        raise EmailDeliveryError(f"SMTP email delivery failed: {safe_error}") from None


def sanitize_email_exception(exc: Exception, smtp_config: SMTPConfig) -> str:
    message = str(exc).strip() or "No additional details were provided."
    message = _redact(message, smtp_config.app_password)
    message = _redact(message, smtp_config.username)
    return f"{exc.__class__.__name__}: {message}"


def _attachment_from_path(path: Path) -> EmailAttachment:
    path = Path(path)
    return EmailAttachment(
        filename=_safe_filename(path.name),
        content=path.read_bytes(),
        mime_type=mimetypes.guess_type(path.name)[0],
    )


def _add_attachment(message: EmailMessage, attachment: EmailAttachment) -> None:
    filename = _safe_filename(attachment.filename)
    mime_type = attachment.mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    if "/" not in mime_type:
        mime_type = "application/octet-stream"

    maintype, subtype = mime_type.split("/", 1)
    message.add_attachment(
        attachment.content,
        maintype=maintype,
        subtype=subtype,
        filename=filename,
    )


def _redact(message: str, secret_value: str) -> str:
    if not secret_value:
        return message
    return message.replace(secret_value, "[redacted]")


def _safe_filename(filename: str) -> str:
    cleaned = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    return cleaned or "attachment"


def _safe_header(value: str) -> str:
    return " ".join(str(value).splitlines()).strip()
