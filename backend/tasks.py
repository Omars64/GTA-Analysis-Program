from celery import Celery
from kombu import Queue

app = Celery("gta-weekly", broker="vercel://")
app.conf.update(
    task_queues=[Queue("scans")],
    task_default_queue="scans",
    task_acks_late=True,
    task_ignore_result=True,
    task_serializer="json",
    accept_content=["json"],
    broker_transport_options={"lease_duration": 300},
)


@app.task(bind=True, max_retries=3)
def run_step(self, job_id, version):
    from job_manager import manager
    try:
        manager.execute(job_id, version)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2)
