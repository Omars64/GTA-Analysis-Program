"""Upload only the private app/email configuration to the linked Vercel project."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
allowed = {'GTA_APP_PASSWORD', 'GTA_SESSION_SECRET', 'SMTP_SERVER', 'SMTP_PORT', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'EMAIL_FROM'}
for line in (root / '.env.gta-access.local').read_text().splitlines():
    key, sep, value = line.partition('=')
    if sep and key in allowed:
        subprocess.run(['node', '--use-system-ca', sys.argv[1], 'env', 'add', key, 'production,preview', '--force', '--sensitive', '--yes', '--scope', 'fred-tactical-corporation-ftc'], input=value.strip(), text=True, cwd=root, check=True)
