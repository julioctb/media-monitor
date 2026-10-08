"""Email transport for alert deliveries.

Transport choice: stdlib smtplib. The alert paths run inside sync workers
(APScheduler BlockingScheduler + sync SQLAlchemy sessions), so an async
SMTP client (aiosmtplib) buys nothing and would add a dependency; the
stdlib client covers STARTTLS and implicit-TLS ports.

Dev mode: with SMTP_HOST unset the transport only logs the message, so
local runs and tests stay network-free.
"""

import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.config import settings

log = logging.getLogger("alerts.transport")


class AlertTransport(Protocol):
    """Structural type: anything with a matching send()."""

    def send(self, *, to: str, subject: str, text: str, html: str) -> None: ...


class SmtpTransport:
    """smtplib-backed delivery; log-only dev mode when no host is set."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str = "",
        password: str = "",
        timeout: int = 10,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout

    @classmethod
    def from_settings(cls) -> "SmtpTransport":
        return cls(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_user,
            settings.smtp_password,
        )

    def send(self, *, to: str, subject: str, text: str, html: str) -> None:
        """Deliver one multipart/alternative email (plain text + HTML)."""
        if not self.host:
            log.info(
                "[dev] SMTP_HOST unset; email logged only — to=%s subject=%s\n%s",
                to,
                subject,
                text,
            )
            return

        message = EmailMessage()
        message["From"] = settings.alert_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text)
        message.add_alternative(html, subtype="html")

        if self.port == 465:  # implicit TLS
            with smtplib.SMTP_SSL(
                self.host, self.port, timeout=self.timeout
            ) as smtp:
                self._authenticate(smtp)
                smtp.send_message(message)
        else:  # STARTTLS negotiation (587 default)
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as smtp:
                smtp.starttls()
                self._authenticate(smtp)
                smtp.send_message(message)

    def _authenticate(self, smtp: smtplib.SMTP) -> None:
        if self.username:
            smtp.login(self.username, self.password)
