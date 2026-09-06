
"""Flexible email helper used by gta_weekly_scraper.

No credentials are hard-coded; everything is passed in at runtime or via
environment variables.
"""
import os
import smtplib
from typing import Iterable, List, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import argparse
import sys


def _env_str(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def send_email_with_attachment(
    subject: str,
    body: str,
    attachment_path: Optional[str] = None,
    *,
    smtp_server: Optional[str] = None,
    smtp_port: Optional[int] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    email_from: Optional[str] = None,
    recipients: Optional[Iterable[str]] = None,
    use_tls: bool = True,
) -> None:
    """Send an email with an optional attachment.

    All connection / identity params can be passed explicitly or taken from
    environment variables:

    - SMTP_SERVER, SMTP_PORT
    - SMTP_USERNAME, SMTP_PASSWORD
    - EMAIL_FROM, EMAIL_TO
    """
    smtp_server = smtp_server or _env_str("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(smtp_port or _env_str("SMTP_PORT", "587"))

    username = username or _env_str("SMTP_USERNAME")
    password = password or _env_str("SMTP_PASSWORD")
    email_from = email_from or _env_str("EMAIL_FROM", username or "")

    if recipients is None:
        raw_to = _env_str("EMAIL_TO", "") or ""
        recipients_list: List[str] = [r.strip() for r in raw_to.split(",") if r.strip()]
    else:
        recipients_list = [str(r).strip() for r in recipients if str(r).strip()]

    if not username or not password:
        raise RuntimeError(
            "SMTP credentials are missing. Provide username/password or set SMTP_USERNAME / SMTP_PASSWORD env vars."
        )

    if not recipients_list:
        raise RuntimeError(
            "No recipients configured. Provide recipients list or set EMAIL_TO env var."
        )

    msg = MIMEMultipart()
    msg["From"] = email_from
    msg["To"] = ", ".join(recipients_list)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if attachment_path:
        with open(attachment_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{os.path.basename(attachment_path)}"',
        )
        msg.attach(part)

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        if use_tls:
            server.starttls()
        server.login(username, password)
        server.sendmail(email_from, recipients_list, msg.as_string())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send an email with optional attachment.")
    parser.add_argument("--subject", required=True, help="Email subject")
    parser.add_argument("--body", required=True, help="Email body text")
    parser.add_argument("--attach", help="Path to attachment", default=None)
    parser.add_argument("--smtp-server", help="SMTP server hostname")
    parser.add_argument("--smtp-port", type=int, help="SMTP server port")
    parser.add_argument("--username", help="SMTP username")
    parser.add_argument("--password", help="SMTP password")
    parser.add_argument("--from-addr", help="From email address")
    parser.add_argument("--to", nargs="*", help="Recipient email(s)")
    parser.add_argument("--no-tls", action="store_true", help="Disable STARTTLS")
    args = parser.parse_args()

    try:
        send_email_with_attachment(
            subject=args.subject,
            body=args.body,
            attachment_path=args.attach,
            smtp_server=args.smtp_server,
            smtp_port=args.smtp_port,
            username=args.username,
            password=args.password,
            email_from=args.from_addr,
            recipients=args.to,
            use_tls=not args.no_tls,
        )
        print("Email sent.")
    except Exception as e:
        print(f"Email failed: {e}", file=sys.stderr)
        sys.exit(1)
