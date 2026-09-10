"""Reproduce Vercel's build-time queue discovery without sending a message."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
os.environ['VERCEL_PYTHON_SUBSCRIBER_ID'] = 'worker_app'
os.environ['VERCEL_APSCHEDULER_DISCOVERY'] = '1'
os.environ['VERCEL'] = '1'

import worker
from vercel.integrations.celery import install_vercel_celery_integration, register_celery_app_queues
from vercel.queue import get_subscriptions

install_vercel_celery_integration(register_queues=False)
register_celery_app_queues(worker.app, start_worker=False)
subscriptions = get_subscriptions()
assert subscriptions, 'The scan worker has no queue subscriptions.'
print(f'PASS: queue runtime imports and {len(subscriptions)} subscription(s) discovered. No message sent.')
