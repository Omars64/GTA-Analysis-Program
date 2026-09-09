"""Inspect or cancel an explicitly named verification run."""
from pathlib import Path
import sys
import requests
import truststore
truststore.inject_into_ssl()
values = dict(line.split('=', 1) for line in (Path(__file__).resolve().parents[1] / '.env.gta-access.local').read_text().splitlines() if '=' in line and not line.startswith('#'))
client = requests.Session()
base = 'https://gta-analysis-program.vercel.app/api'
response = client.post(base + '/session', json={'password': values['GTA_APP_PASSWORD']}, timeout=40)
response.raise_for_status()
if len(sys.argv) > 2 and sys.argv[2] == 'cancel':
    response = client.post(base + '/runs/' + sys.argv[1] + '/cancel', timeout=40)
else:
    response = client.get(base + '/runs/' + sys.argv[1], timeout=40)
response.raise_for_status()
job = response.json()
print({k: job.get(k) for k in ('id', 'status', 'stage', 'progress', 'message', 'error')})
