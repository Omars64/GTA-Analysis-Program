"""Verify SMTP authentication without sending a message."""
from pathlib import Path
import smtplib
import ssl
values = dict(line.split('=', 1) for line in (Path(__file__).resolve().parents[1] / '.env.gta-access.local').read_text().splitlines() if '=' in line and not line.startswith('#'))
with smtplib.SMTP(values['SMTP_SERVER'], int(values['SMTP_PORT']), timeout=30) as smtp:
    smtp.starttls(context=ssl.create_default_context())
    smtp.login(values['SMTP_USERNAME'], values['SMTP_PASSWORD'])
    print('PASS: SMTP TLS connection and sender authentication. No email sent.')
