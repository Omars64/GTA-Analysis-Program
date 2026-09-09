"""Generate private app credentials and send them to Vercel through stdin.

Usage: python scripts/configure_vercel_access.py PATH_TO_VERCEL_CLI_JS
The recovery file is gitignored; values are never printed or passed as CLI args.
"""
from pathlib import Path
import os
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / ".env.gta-access.local"


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Pass the installed Vercel CLI JavaScript entrypoint.")
    if RECOVERY.exists():
        values = dict(line.split("=", 1) for line in RECOVERY.read_text().splitlines() if "=" in line and not line.startswith("#"))
    else:
        values = {"GTA_APP_PASSWORD": secrets.token_urlsafe(32), "GTA_SESSION_SECRET": secrets.token_urlsafe(48)}
        # Exclusive creation prevents overwriting an existing access file.
        with RECOVERY.open("x", encoding="utf-8") as handle:
            handle.write("# Private app access. Never commit or share this file.\n")
            for key, value in values.items():
                handle.write(f"{key}={value}\n")
        os.chmod(RECOVERY, 0o600)
    for name, value in values.items():
        if name not in {"GTA_APP_PASSWORD", "GTA_SESSION_SECRET"}:
            continue
        subprocess.run(
            ["node", "--use-system-ca", sys.argv[1], "env", "add", name, "production,preview",
             "--sensitive", "--yes"],
            input=value, text=True, check=True, cwd=ROOT,
        )
    print(f"Private access configured. Your recovery file is {RECOVERY}")


if __name__ == "__main__":
    main()
